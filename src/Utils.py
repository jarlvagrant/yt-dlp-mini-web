import datetime
import json
import logging
import os
from pathlib import Path

log_path = "logs"
log_file = "debug.log"
config_path = "configs"
config_file = "config.json"


logger = logging.getLogger(__name__)


def getDate():
	return datetime.date.today().__str__()


def getTime():
	return datetime.datetime.now().__str__()


class JsonIO:
	def __init__(self, path=config_path, json_file=config_file):
		if not os.path.isdir(path):
			os.mkdir(path)
		self.json_path = os.path.join(path, json_file)
		if not os.path.isfile(self.json_path):
			with open(self.json_path, "w") as f:
				self.dict = {
					"video_dir": "/video",
					"audio_dir": "/audio"
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


ConfigIO = JsonIO()


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
