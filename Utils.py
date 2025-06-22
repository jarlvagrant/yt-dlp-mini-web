import datetime
import json
import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
from fake_useragent import UserAgent

log_path = "logs"
log_file = "debug.log"
config_path = "configs"
config_file = "config.json"
book_csv_file = "books.csv"
book_csv_columns = ['title', 'author', 'path', 'format', 'size', 'updated', 'created']


logger = logging.getLogger(__name__)


def getDate():
	return datetime.date.today().__str__()


def getTime():
	return datetime.datetime.now().__str__()


class UserAgentGen(UserAgent):
	def __init__(self):
		super().__init__()
		self.ua = self.random
		logger.debug(f"User Agent: {self.ua}")

	def get(self):
		return self.ua

	def renew(self):
		self.ua = self.random
		logger.debug(f"User Agent: {self.ua}")


UA = UserAgentGen()


class JsonIO:
	def __init__(self, path=config_path, json_file=config_file):
		if not os.path.isdir(path):
			os.mkdir(path)
		self.json_path = os.path.join(path, json_file)
		if not os.path.isfile(self.json_path):
			with open(self.json_path, "w") as f:
				self.dict = {
					"video_dir": "/video",
					"audio_dir": "/audio",
					"ebook_dir": "/book",
					"email": {
						"from": "sender email address",
						"to": "kindle email address",
						"host": "host",
						"secret": "password",
						"port": 587
					},
					"web_parsers": [
						{
							"base": "www.52shu.vip",
							"content_tag": {
								"id": "text"
							}
						}]
				}
				json.dump(self.dict, f, ensure_ascii=False, indent=4, )
				f.close()
		else:
			with open(self.json_path, 'r') as f:
				self.dict = json.load(f)
				f.close()

	def get(self, key, subkey=None):
		if not subkey:
			return self.dict.get(key, None)
		if self.dict.get(key, None):
			return self.dict.get(key, None).get(subkey, None)
		return None

	def set(self, key, value, subkey=None):
		if not subkey:
			self.dict[key] = value
		else:
			if self.dict.get(key, None):
				self.dict[key][subkey] = value
		with open(self.json_path, 'w', encoding='utf-8') as f:
			json.dump(self.dict, f, ensure_ascii=False, indent=4, )
			f.close()


class CsvIO:
	def __init__(self, csv_file=book_csv_file, columns=book_csv_columns):
		self.file = csv_file
		self.columns = columns
		try:
			self.df = pd.read_csv(self.file)
		except FileNotFoundError:
			self.df = pd.DataFrame(columns=self.columns)
			self.df.to_csv(self.file, index=False)

	def get(self, foo: dict):
		if not foo or not self.validate(foo):
			return pd.DataFrame(columns=self.columns)
		to_query = ""
		for key, value in foo.items():
			to_query += f'{key}.str.contains("{value}",na=False)&'
		bar = self.df.query(to_query[:-1])
		return bar

	def set(self, new, old=None):
		# Append new row at the end, or update the existing row with
		# the new dictionary. Both new and old dictionary may contain
		# full or partial key, value sets of the columns
		if not old or not self.update(new, old):
			self.append(new)

	def remove(self, foo: dict):
		c = self.get(foo)
		self.df.drop(c.index, inplace=True)
		self.writeCsv()

	def writeCsv(self):
		self.df.to_csv(self.file, encoding='utf-8', index=False)

	def append(self, foo):
		self.df.loc[len(self.df.index)] = foo
		self.writeCsv()

	def update(self, new, old):
		c = self.get(old)
		if not c.empty:
			for key in new.keys():
				self.df.loc[c.index, key] = new.get(key)
			self.writeCsv()
		return not c.empty

	def validate(self, foo: dict):
		for key, _ in foo.items():
			if key not in self.columns:
				return False
		return True


ConfigIO = JsonIO()
BooksIO = CsvIO()


def getInitialFolder(dir_type):
	folder = ConfigIO.get(dir_type)
	if not folder or not os.path.isdir(folder):
		folder = Path.home().__str__()
		ConfigIO.set(dir_type, folder)
	return folder


def getInitialSubfolders(cur_dir):
	res = [cur_dir]
	parent_dir = cur_dir
	if cur_dir and os.path.exists(cur_dir):
		parent_dir = Path(cur_dir).parent
	for f in (os.sep, parent_dir.__str__(), Path.home().__str__()):
		if f not in res:
			res.append(f)
	return res


def getSubfolders(cur_dir):
	res = getInitialSubfolders(cur_dir)
	temp = []
	if cur_dir and os.path.isdir(cur_dir):
		for f in os.scandir(cur_dir):
			if f.is_dir() and not f.name.startswith('.'):
				temp.append(f.path)
	temp = sorted(temp)
	for f in temp:
		if f not in res:
			res.append(f)
	return res


class SendEmail:
	def __init__(self, filepath):
		self.filepath = filepath
		self.message = ""

	def send(self):
		if not os.path.isfile(self.filepath):
			logger.error(f"Invalid file path: {self.filepath}")
			self.message = f"Invalid file path: {self.filepath}"
			return False

		email = ConfigIO.get("email")
		if not email or None in [email.get(key, None) for key in ["from", "to", "host", "port", "secret"]]:
			logger.error(f"Invalid email config in config.json: please check keys: from, to, host, port, secret")
			self.message = f"Invalid email config in config.json: please check keys: from, to, host, port, secret"
			return False
		msg = EmailMessage()
		filename = Path(self.filepath).name
		msg['Subject'] = filename
		msg['From'] = email.get("from")
		msg['To'] = email.get("to")
		with open(self.filepath, 'rb') as fp:
			data = fp.read()
		msg.add_attachment(data, maintype='application', subtype='octet-stream', filename=filename)
		# Add error and failure check
		with smtplib.SMTP(email.get("host"), email.get("port")) as smtp:
			smtp.starttls()
			smtp.login(email.get("from"), email.get("secret"))
			smtp.send_message(msg=msg)
			smtp.quit()
		logger.info(f"Emailed {filename} to {email.get('to')}")
		self.message = f"Emailed {filename} to {email.get('to')}"
		return True
