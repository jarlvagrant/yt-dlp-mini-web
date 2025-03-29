import os
import re
from pathlib import Path
from urllib.parse import urlsplit, unquote

import chinese_converter
import requests
from bs4 import BeautifulSoup
from ebooklib import epub
from flask import typing as ft, render_template, Response, request
from flask.views import View

from Utils import ConfigIO, UA


class EBook(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		return render_template("ebk.html", ebook_dir=ConfigIO.get("ebook_dir"))


class ProcessEbook(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		url = request.form.get('url')
		converter = EpubConverter(url)
		converter.convert()
		return Response()


def read(txt=None, filepath=None):
	'''
	read text or read from a file. if both text and filepath are given, append text to file text.
	'''
	output = ""
	if txt is not None:
		output = clean_txt(txt)
	if filepath is not None:
		with open(filepath, 'rb') as f:
			output = clean_txt(f.read()) + output
			f.close()
	return output


def clean_txt(txt):
	'''
	Run transformations on the text to put it into
	consistent state.
	'''
	if isinstance(txt, bytes):
		# Only handle GBK chars for now. Download Cadet to detect other encodings.
		try:
			txt = txt.decode('utf-8')
		except UnicodeDecodeError:
			txt = txt.decode('GBK', 'ignore')
	# Strip whitespace from the beginning and end of the line. Also replace
	# all line breaks with \n.
	txt = '\n'.join([line.strip() for line in txt.splitlines()])

	# Replace whitespace at the beginning of the line with &nbsp;
	# txt = re.sub(r'(?m)(?<=^)([ ]{2,}|\t+)(?=.)', '&nbsp;' * 4, txt)

	# Condense redundant spaces
	txt = re.sub(r'[ ]{2,}', ' ', txt)

	# Remove blank space from the beginning and end of the document.
	txt = re.sub(r'^\s+(?=.)', '', txt)
	txt = re.sub(r'(?<=.)\s+$', '', txt)
	# Remove excessive line breaks.
	txt = re.sub(r'\n{3,}', '\n\n', txt)
	# remove ASCII invalid chars : 0 to 8 and 11-14 to 24
	txt = clean_ascii_chars(txt)

	return chinese_converter.to_simplified(txt)


codepoint_to_chr = chr


def ascii_pat(for_binary=False):
	attr = 'binary' if for_binary else 'text'
	ans = getattr(ascii_pat, attr, None)
	if ans is None:
		chars = set(range(32)) - {9, 10, 13}
		chars.add(127)
		pat = '|'.join(map(codepoint_to_chr, chars))
		if for_binary:
			pat = pat.encode('ascii')
		ans = re.compile(pat)
		setattr(ascii_pat, attr, ans)
	return ans


def clean_ascii_chars(txt, charlist=None):
	r'''
	Remove ASCII control chars.
	This is all control chars except \t, \n and \r
	'''
	is_binary = isinstance(txt, bytes)
	empty = b'' if is_binary else ''
	if not txt:
		return empty

	if charlist is None:
		pat = ascii_pat(is_binary)
	else:
		pat = '|'.join(map(codepoint_to_chr, charlist))
		if is_binary:
			pat = pat.encode('utf-8')
	return pat.sub(empty, txt)


def write(text: str, path):
	with open(path, 'w', encoding='utf-8') as f:
		f.write(text)
		f.close()


def split_txt(txt):
	'''
	Split text by the most common chapter regex
	'''
	r = r"(?m)^第[0123456789一二三四五六七八九十零〇百千两]+[章回部节集卷]"
	temp_indices = [c.start() for c in re.finditer(r, txt)]
	temp_indices.append(len(txt))

	# When chapters are too large or in case the chapter regex was not found, so the content was a big chunk,
	# split the text by newlines and form chapters of chars from 6000 to 8000.
	temp_cur = 0
	indices = []
	for t in temp_indices:
		if t - temp_cur < 8000:
			indices.append(t)
		else:
			indices.append(t)
			line_cur = temp_cur
			line_indices = [c.start() for c in re.finditer(r'\n', txt[temp_cur:t])]
			for l in line_indices:
				if l - line_cur > 6000:
					line_cur = l
					indices.append(l)
					if t - line_cur < 8000:
						indices.append(t)
						break
		temp_cur = t
	return indices


def get_image(url):
	image = None
	if url:
		if os.path.isfile(url):
			with open(url, 'rb') as f:
				image = f.read()
		else:
			extractHtmlImage(url)
	return image


def extractHtml(url: str, cookies=None):
	retry = 5
	while retry > 0:
		try:
			r = requests.get(url, headers={'User-Agent': UA.get()}, cookies=cookies)
			r.raise_for_status()
			return r
		except Exception as ex:
			print(f"Error: Downloading {url} with {ex}")
			UA.renew()
			retry -= 1
	return None


def extractHtmlImage(url: str):
	image = None
	response = extractHtml(url)
	if response:
		image = response.content
	return image


def extractHtmlText(url: str, cookies=None):
	text = ""
	response = extractHtml(url, cookies)
	if response:
		text = unquote(response.text)
	return text


def extractHtmlSoup(url: str, cookies=None):
	soup = None
	text = extractHtmlText(url, cookies)
	if text:
		soup = BeautifulSoup(text, 'html5lib')
	return soup


class EpubConverter:
	'''
	need to add tags to epub
	'''
	def __init__(self, data, input_file, title="", author="", image_file=None):
		self.data = read(data, input_file)
		self.path = ConfigIO.get("ebook_dir")
		if not title and not input_file:
			print(f"Failed converting without title and input file")
			return
		self.title = title if title else Path(input_file).stem
		self.title = chinese_converter.to_simplified(self.title)
		self.author = chinese_converter.to_simplified(author) if author else ""
		self.image = get_image(image_file)
		self.ebook = epub.EpubBook()
		write(self.data, os.path.join(self.path, self.title + ".txt"))
		self.convert()

	def getTags(self):
		pass

	def get_chaps(self, indices):
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
			elif len(temp) > 10:
				header = temp[:10]
				content = temp
			else:
				header = temp
				content = ""
			print(f"processing index: {count} title: {header}, word count: {len(temp)}")
			chap = epub.EpubHtml(title=header, file_name="%05d.xhtml" % count, lang="zh")
			chap.content = ("<h3>%s</h3><p>%s</p>" % (header, content))
			chaps = chaps + (chap,)
			self.ebook.toc.append(epub.Link("%05d.xhtml" % count, header, "%05d" % count))
			self.ebook.add_item(chap)
		return chaps

	def convert(self):
		if not self.data or len(self.data) == 0:
			print("Error: the resource txt file has no content")
			exit()
		print(f"initiating txt to epub converting of {self.title}, author: {self.author} length {len(self.data)}")

		# set metadata
		self.ebook.set_identifier(self.title + self.author)
		self.ebook.set_title(self.title)
		self.ebook.set_language("zh")
		self.ebook.add_author(self.author)
		self.ebook.set_cover(file_name="cover.jpg", content=self.image)

		indices = split_txt(self.data)
		chaps = self.get_chaps(indices)

		self.ebook.add_item(epub.EpubNcx())
		self.ebook.add_item(epub.EpubNav())

		style = '''p {text-indent: 0.5em;}'''
		default_css = epub.EpubItem(
			uid="style_default",
			file_name="style/default.css",
			media_type="text/css",
			content=style)
		self.ebook.add_item(default_css)

		# basic spine
		self.ebook.spine = ["nav", *chaps]

		# write to the file
		epub.write_epub(os.path.join(self.path, self.title + ".epub"), self.ebook, {})
		print(f"Success: {self.title} converting done. number of chapters: {len(indices)}")


class ScrapeHtml:
	def __init__(self, url):
		self.split_utl = urlsplit(url)
		self.parsers = {}
		self.set_parsers()
		self.info = {}
		self.set_intro()
		print(self.info.__str__())
		self.set_pages()
		self.download()

	def get_parser(self, key):
		return self.parsers.get(key, "")

	def get_info(self, key):
		return self.info.get(key, "")

	def set_parsers(self):
		# Read parsers for the current website in to dict.
		for p in ConfigIO.get("web_parsers"):
			if p.get("base", "") == self.split_utl.netloc:
				for key, value in p.items():
					self.parsers[key] = value
		if not self.parsers:
			exit(f"Failed parsing {self.split_utl.geturl()}, {self.split_utl.netloc} is not in config.json -> parsers.")
		print(self.parsers.__str__())

	def set_intro(self):
		# Find the book number. Put together book intro page url.
		temp = re.match(self.get_parser("book_no"), self.split_utl.path)
		if not temp:
			print(f"Failed parsing book number from {self.split_utl.geturl()}")
			return
		self.info["book_no"] = temp.group(1)
		self.info["intro"] = self.get_parser("intro") % self.get_info("book_no")

		# Head contains title, author and hopefully tags.
		if not self.get_info("intro"):
			print(f"Failed getting intro url from {self.split_utl.geturl()}")
			return
		soup = extractHtmlSoup(self.get_info("intro"))
		if not soup:
			print(f"Failed fetching {self.get_info('intro')}")
			return
		element = soup.find(attrs=self.get_parser('head'))
		if element:
			self.info["head"] = element.text
			txt = re.match(self.get_parser("title"), self.get_info('head'))
			if txt:
				self.info["title"] = txt.group(1)
				self.info["author"] = txt.group(2)
				self.info["tag"] = txt.group(3)
		element = soup.find(attrs=self.get_parser('des'))
		if element:
			self.info["des"] = "\n".join(element.stripped_strings)
		element = soup.find(self.get_parser('img'))
		if element:
			self.info["img"] = self.split_utl._replace(path=element.get("src")).geturl()

	def set_head(self):
		# Book title must be available. Try getting it by tag h1, title
		if self.get_info("title"):
			return
		url = self.get_parser("page") % (self.get_info("book_no"), self.get_parser('first_page'))
		soup = extractHtmlSoup(url)
		if not soup:
			print(f"Failed fetching {url}")
			return
		element = soup.find('h1')
		element = element if element else soup.find('title')
		if element:
			head = element.text
			txt = re.match(self.get_parser("title"), head)
			if txt:
				self.info["title"] = txt.group(1)
				self.info["author"] = txt.group(2)
				self.info["tag"] = txt.group(3)

	def set_pages(self):
		temp = 0
		soup = extractHtmlSoup(self.split_utl.geturl())
		if soup:
			element = soup.find(string=self.get_parser("last_page"))
			if element:
				href = element.parent.get("href")
				if href:
					last = re.match(self.get_parser("last_page_no"), href)
					if last:
						temp = int(last.group(1))
		if temp <= 1:
			return
		self.info["pages"] = [n for n in range(self.parsers.get("first_page", 1), temp + 1)]

	def download(self):
		if not self.get_info("pages"):
			print(f"Download failed: getting no pages from {self.split_utl.geturl()}")
			return
		self.set_head()
		if not self.get_info("title"):
			print(f"Download failed: getting no book title from {self.split_utl.geturl()}")
			return
		text = "\n".join(
			[self.get_info("title"), self.get_info("author"), self.get_info("tag"), self.get_info("des")]) + "\n"
		for page in self.get_info("pages"):
			url = self.get_parser("page") % (self.get_info("book_no"), page)
			soup = extractHtmlSoup(url)
			temp = f"Failed to download page {page}\n"
			if soup:
				element = soup.find(id=self.get_parser("content"))
				if element:
					temp = "\n".join(element.stripped_strings)
			text += temp
		text = clean_txt(text)
		text = re.sub(self.get_parser('watermark'), '', text)
		if len(text) < 10000:
			print(f"Failed downloading {self.get_info('title')}. Article is too short: {len(text)}")
			return
		print(f"Successfully downloaded {self.get_info('title')}. Word count: {len(text)}")
		EpubConverter(text, None, self.get_info('title'), self.get_info('author'), self.get_info('img'))
		return True
