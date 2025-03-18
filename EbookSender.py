import os
import re

import requests
import validators
from ebooklib import epub
from flask import typing as ft, render_template, Response, request
from flask.views import View

from YdlWrapper import config


class EBook(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		return render_template("ebk.html", ebook_dir=config["ebook_dir"])


class ProcessEbook(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		url = request.form.get('url')
		converter = EpubConverter(url)
		converter.toEpub()
		return Response()


class EpubConverter:
	def __init__(self, url, data, new_title=None, new_author=None, image_file=None):
		self.url = url
		self.data = data
		self.path = config["ebook_dir"]
		self.title = new_title
		self.author = new_author
		self.image = None
		if image_file:
			if os.path.isfile(image_file):
				self.image = open(image_file, 'rb').read()
			elif image_file.startswith("http") or image_file.startswith("ftp"):
				try:
					self.image = requests.get(image_file, headers={
						'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0'}).content
				except Exception as ex:
					print(f"failed downloading image {ex}")

	def getInfo(self):
		if validators.url(self.url):
			pass


	def toEpub(self):
		if not self.data or len(self.data) == 0:
			print("Error: the resource txt file has no content")
			exit()
		print(f"initiating txt to epub converting of {self.title}, author: {self.author} length {len(self.data)}")
		book = epub.EpubBook()

		# set metadata
		book.set_identifier(self.title + self.author)
		book.set_title(self.title)
		book.set_language("zh")
		book.add_author(self.author)
		book.set_cover(file_name="cover.jpg", content=self.image)

		regex = "[第卷][0123456789一二三四五六七八九十零〇百千两]+[章回部节集卷][ \t\n\r：:].*"
		indices = []
		indices.extend(c.start() for c in re.finditer(regex, self.data))
		indices.append(len(self.data))

		# if regex has no match, then we are facing a large chapter, break it by length
		temp = []
		start = 0
		for index in indices:
			if index - start > 8000:
				while index - start > 4000:
					start += 4000
					temp.append(start)
			temp.append(index)
			start = index
		indices = temp

		# start = 0
		# for count, index in enumerate(temp):
		# 	print(f"count {count}, index {index} diff {index - start}")
		# 	start = index

		# if small chapter detected, merge it with the next chapter, comment it out for now
		temp = []
		start = 0
		for index in indices:
			if index - start > 100 or (start == 0 and not index == 0):
				start = index
				temp.append(index)
		indices = temp

		chaps = ()
		start = 0
		for count, index in enumerate(indices):
			temp = self.data[start: index]
			if start == index:
				continue
			start = index

			if "\n" in temp:
				header = temp.split("\n", 1)[0]
				content = temp.split("\n", 1)[1].replace("\n", '</p><p>')
			else:
				header = temp
				content = ""
			chap = epub.EpubHtml(title=header, file_name="%05d.xhtml" % count, lang="zh")
			chap.content = ("<h3>%s</h3><p>%s</p>" % (header, content))
			book.toc.append(epub.Link("%05d.xhtml" % count, header, "%05d" % count))
			book.add_item(chap)
			chaps = chaps + (chap,)

		book.add_item(epub.EpubNcx())
		book.add_item(epub.EpubNav())

		style = '''p {text-indent: 0.5em;}'''
		default_css = epub.EpubItem(
			uid="style_default",
			file_name="style/default.css",
			media_type="text/css",
			content=style)
		book.add_item(default_css)

		# basic spine
		book.spine = ["nav", *chaps]

		# write to the file
		epub.write_epub(os.path.join(self.path, self.epub_file), book, {})
		print(f"converting done. number of chapters: {len(indices)}")

