import datetime
import json
import logging
import os
import shutil
import time
from importlib.metadata import version
from pathlib import Path

log_path = "logs"
log_file = "debug.log"
history_file = "history.json"
config_path = "configs"
config_file = "config.json"


logger = logging.getLogger(__name__)


def getDate():
	return datetime.date.today().__str__()


def getTime():
	return datetime.datetime.now().__str__()


class JsonIOClass:
	def __init__(self, path="", json_file=""):
		if not os.path.isdir(path):
			os.mkdir(path)
		self.json_path = os.path.join(path, json_file)
		self.dict = {}
		self.load()

	def load(self):
		if not os.path.isfile(self.json_path):
			self.dict = {'Initialized': time.ctime()}
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
			if key in self.dict:
				self.dict[key][subkey] = value
			else:
				self.dict[key] = {subkey : value}
		self.save()

	def save(self):
		with open(self.json_path, 'w', encoding='utf-8') as f:
			json.dump(self.dict, f, ensure_ascii=False, indent=4, )
			f.close()

class ConfigIOClass(JsonIOClass):
	def __init__(self, path=config_path, json_file=config_file):
		super().__init__(path, json_file)
		if not self.get('video_dir'):
			self.set('video_dir', '/video')
		if not self.get('audio_dir'):
			self.set('audio_dir', '/audio')


class HistoryIOClass(JsonIOClass):
	def __init__(self, path=log_path, json_file=history_file):
		super().__init__(path, json_file)
		super().set('yt-dlp', time.ctime(), version('yt-dlp'))

	def set(self, key, value, subkey=None):
		if len(self.dict.keys()) > 2:
			self.move_file()
			self.dict = {'Initialized': time.ctime(), 'yt-dlp': {version('yt-dlp'): time.ctime()}}
		super().set(key, value, subkey=subkey)

	def move_file(self):
		shutil.move(self.json_path, self.json_path + '.' + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))


ConfigIO = ConfigIOClass()
HistoryIO = HistoryIOClass()


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
