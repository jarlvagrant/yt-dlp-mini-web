import datetime
import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
from fake_useragent import UserAgent

config_file = "config.json"
book_csv_file = "books.csv"
book_csv_columns = ['title', 'author', 'path', 'format', 'size', 'updated', 'created']


def getDate():
	return datetime.date.today()


class UserAgentGen(UserAgent):
	def __init__(self):
		super().__init__()
		self.ua = self.random
		print(f"User Agent: {self.ua}")

	def get(self):
		return self.ua

	def renew(self):
		self.ua = self.random
		print(f"User Agent: {self.ua}")


UA = UserAgentGen()


class JsonIO:
	def __init__(self, json_file):
		self.file = json_file
		with open(self.file, 'r') as f:
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
		with open(self.file, 'w', encoding='utf-8') as f:
			json.dump(self.dict, f, ensure_ascii=False, indent=4, )
			f.close()


class CsvIO:
	def __init__(self, csv_file, columns):
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


ConfigIO = JsonIO(config_file)
BooksIO = CsvIO(book_csv_file, book_csv_columns)


def getInitialFolder(dir_type):
	folder = ConfigIO.get(dir_type)
	if not folder or not os.path.isdir(dir_type):
		folder = Path.home()
	return folder


def getPossibleFolders(dir_type=None):
	folder = ConfigIO.get(dir_type)
	guess = [os.sep, os.getcwd(), Path.home()]
	if folder and os.path.isdir(folder):
		guess.append(folder)
	res = set()
	for g in guess:
		if os.path.isdir(g):
			res.add(os.path.abspath(g))
	return sorted(res)


def getSubfolders(folder):
	res = set()
	if not folder or not os.path.isdir(folder):
		folder = Path.home()
	for f in os.scandir(folder):
		if f.is_dir():
			res.add(f.path)
	return sorted(res)


class SendEmail:
	def __init__(self, file, filename):
		self.file = file
		self.filename = filename

	def send(self):
		if not self.filename or not os.path.isfile(self.file):
			print(f"Invalid file name: {self.filename} or file path: {self.file}")
			return False

		email = ConfigIO.get("email")
		if not email or None in [email.get(key, None) for key in ["from" , "to" , "host", "port", "secret"]]:
			print(f"Invalid email config in config.json: please check keys: from, to, host, port, secret")
			return False
		msg = EmailMessage()
		msg['Subject'] = self.filename
		msg['From'] = email.get("from")
		msg['To'] = email.get("to")
		with open(self.file, 'rb') as fp:
			data = fp.read()
		msg.add_attachment(data, maintype='application', subtype='octet-stream', filename=self.filename)
		# Add error and failure check
		with smtplib.SMTP(email.get("host"), email.get("port")) as smtp:
			smtp.starttls()
			smtp.login(email.get("from"), email.get("secret"))
			smtp.send_message(msg=msg)
			smtp.quit()
		print(f"Emailed {self.filename} to {email.get('to')}")
		return True
