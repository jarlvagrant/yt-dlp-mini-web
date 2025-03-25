import datetime
import json

import pandas as pd
from pandas import DataFrame

config_file = "config.json"
book_csv_file = "books.csv"
book_csv_columns = ['title', 'author', 'path', 'format', 'size', 'updated', 'created']


def getDate():
	return datetime.date.today()


class JsonIO:
	def __init__(self, json_file):
		self.file = json_file
		with open(self.file, 'r') as f:
			self.dict = json.load(f)
			f.close()

	def get(self, key):
		return self.dict.get(key, None)

	def set(self, key, value):
		self.dict[key] = value
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
