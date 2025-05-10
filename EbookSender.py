import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, unquote

import chinese_converter
import requests
from bs4 import BeautifulSoup
from ebooklib import epub
from flask import typing as ft, render_template, Response, request, jsonify, url_for, flash
from flask.views import View
from werkzeug.utils import secure_filename, redirect

from Utils import ConfigIO, UA


book_dict = {}


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

class EbookInputs(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		new_books = request.form.getlist('files[]')
		print(new_books)
		return render_template("ebk_inputs.html", txt_files=new_books)


class EbookUpload(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		path = ConfigIO.get("ebook_dir")
		if not os.path.isdir(path):
			flash("Invalid upload path: {path}")
		else:
			files = request.files.getlist("docs")
			names = []
			for f in files:
				# filename = secure_filename(file.filename)
				names.append(f.filename)
				f.save(os.path.join(ConfigIO.get("ebook_dir"), f.filename))
			print("Uploaded files: {names}".format(names=names))
		return redirect(url_for("ebook"))


class EbookCover(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		title = request.form.get('title', 'unknown') + ".jpg"
		url = request.form.get('img_url', "")
		file = request.files.get('image')

		if url:
			print(f"Save image: {url} to {title}")
			image = get_image(url)
			if image:
				with open(os.path.join(ConfigIO.get("ebook_dir"), title), "wb") as f:
					f.write(image)
				return jsonify(code=200)
			else:
				return jsonify(code=500)
		elif file:
			print(f"Save image: {file.filename} to {title}")
			image = file.read()
			if image:
				with open(os.path.join(ConfigIO.get("ebook_dir"), title), "wb") as f:
					f.write(image)
					return Response(status=200)
			else:
				return Response(status=500)



class EbookConvert(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		file_name = request.form.get('file', '')
		title = request.form.get('title', '')
		author = request.form.get('author', '')
		tags = request.form.get('tags', '')
		des = request.form.get('des', '')
		image_name= request.form.get('image', '')
		if not file_name:
			return jsonify(code=500, messages="No input text file")
		file_path = os.path.join(ConfigIO.get("ebook_dir"), file_name)
		if not os.path.isfile(file_path):
			return jsonify(code=500, messages="Input text file not found")
		data = clean_txt(read_binary_file(file_path))
		if not title:
			title = Path(file_path).stem
		image_path = os.path.join(ConfigIO.get("ebook_dir"), image_name)
		if not os.path.isfile(image_path):
			image_path = None
		print(f"Converting {file_path}, title={title}, author={author}, tags={tags}, des={des}, image={image_path}")
		converter = EpubConverter(data, title, author, tags, des, image_path)
		converter.convert()
		return jsonify(code=200, info=converter.info)


def read_binary_file(filepath=None):
	output = ""
	if filepath is not None:
		with open(filepath, 'rb') as f:
			output = f.read()
			f.close()
	return output


def clean_txt(txt):
	'''
	Run transformations on the text to put it into
	consistent state.
	'''
	if not txt:
		return ''

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


def write_text_file(text: str, path):
	with open(path, 'w', encoding='utf-8') as f:
		f.write(text)
		f.close()

# make a list of possible chap format, start from the strict regex.
# chap_regex = r"(?m)☆?、?第[0123456789一二三四五六七八九十零〇百千两]+[章回部节集卷]"
chap_regex_list = [r"(?m)^[\s\r\n\.☆、—-]*第[0123456789一二三四五六七八九十零〇百千两]+[章回部节集卷][\s\r\n\.☆、—-].{0,30}", # 第一章 飞雪连天
                   r"(?m)^.{0,10}第[0123456789一二三四五六七八九十零〇百千两]+[章回部节集卷].{0,30}", # 1. 第一章 飞雪连天
                   r"(?m)^[\s\r\n\.☆、—-]*\d+[\s\r\n\.☆、—-].{0,30}", # 1. 飞雪连天
                   r"(?m)^.{0,10}\d+.{0,30}", # 正文 1. 飞雪连天
                   r"(?m)^[\s\r\n\.☆、—-]*[第章集卷][0123456789一二三四五六七八九十零〇百千两]+[\s\r\n\.☆、—-].{0,30}", # ☆ 卷一 飞雪连天
                   r"(?m)^.{0,10}[第章集卷][0123456789一二三四五六七八九十零〇百千两]+.{0,30}", # ☆一。 卷一 飞雪连天
                   r"(?m)^[\s\r\n\.☆、-—]*.{0,30}"] # ☆ 飞雪连天


def get_image(url):
	image = None
	if url:
		if os.path.isfile(url):
			image = read_binary_file(url)
		else:
			image = extractHtmlImage(url)
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
	if response.status_code == 200:
		image = response.content
	return image


def extractHtmlText(url: str, cookies=None):
	text = ""
	response = extractHtml(url, cookies)
	if response.status_code == 200:
		text = unquote(response.text)
	return text


def extractHtmlSoup(url: str, cookies=None):
	soup = None
	text = extractHtmlText(url, cookies)
	if text:
		soup = BeautifulSoup(text, 'html5lib')
	return soup


class EpubConverter:
	def __init__(self, data, title, author="", tags = "", des="", image_url=None):
		self.data = data
		self.path = ConfigIO.get("ebook_dir")
		self.title = title
		self.author = author if author else ""
		self.tags = tags if tags else ""
		self.des = des if des else ""
		self.image = get_image(image_url)
		# we only need this when txt content is no local
		# write_text_file("\n".join([f"《{self.title}》作者：{self.author}", f"内容标签：{self.tags}", self.des, self.data]),
		#                 os.path.join(self.path, self.title + ".txt"))
		self.verify()
		self.info = ""
		self.ebook = epub.EpubBook()

	def verify(self):
		if not self.data:
			return

		if not self.title or not self.author:
			temp = re.search(r"(?s)[.]?([^\n《》「」『』【】\/]*).?\n?作者[：:]([^\n》」』】\(]*)", self.data)
			if temp:
				self.title = temp.group(1) if not self.title else self.title
				self.author = temp.group(2) if not self.author else self.author
		if not self.title:
			self.title = self.data.split("\n", 1)[0]
			if "http" in self.title:
				self.title = ""
				temp = self.data.split("\n", 2)
				if len(temp) > 2:
					self.title = temp[1]
		if not self.tags:
			temp = re.search('内容标签[:：](.*)', self.data)
			if temp:
				self.tags = temp.group(1)

	def get_chaps(self, indices):
		chaps = ()
		start = 0
		for count, index in enumerate(indices):
			if start == index:
				continue
			temp = self.data[start: index].lstrip()
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
			print(f"Chapter {count}: title={header}, size={len(temp)}")
			self.info += f"Chapter {count}: title={header}, size={len(temp)}\n"
			chap = epub.EpubHtml(title=header, file_name="%05d.xhtml" % count, lang="zh")
			chap.content = ("<h3>%s</h3><p>%s</p>" % (header, content))
			chaps = chaps + (chap,)
			self.ebook.toc.append(epub.Link("%05d.xhtml" % count, header, "%05d" % count))
			self.ebook.add_item(chap)
		return chaps

	def split_txt(self):
		'''
		Split text by the most common chapter regex
		'''
		temp_indices = []
		for regex in chap_regex_list:
			temp_indices = [c.start() for c in re.finditer(regex, self.data)]
			if len(temp_indices) > len(self.data)/6000: # chapter words count, use 6000 as maximum limit
				break
		temp_indices.append(len(self.data))

		# When chapters are too large or in case the chapter regex was not found, so the content was a big chunk,
		# split the text by newlines and form chapters of chars > 4000
		x = 0
		indices = []
		for t_index in temp_indices:
			# print(f"start {x} end {t} diff {t - x} {txt[x_cur:x+15]}")
			if t_index - x > 8000:
				y = x
				line_indices = [c.start() for c in re.finditer(r'\n', self.data[x:t_index])]
				for l_index in line_indices:
					if x + l_index - y > 4000:
						indices.append(x + l_index)
						y = x + l_index
			indices.append(t_index)
			x = t_index
		return indices

	def convert(self):
		if not self.data:
			print("Error: the resource txt file has no content")
			exit()
		if not self.title:
			print("Error: can not convert txt file with no title")
			exit()
		print(f"initiating txt to epub converting of {self.title}, author: {self.author} length {len(self.data)}")

		# set metadata
		self.ebook.set_identifier(self.title + self.author)
		self.ebook.set_title(self.title)
		self.ebook.set_language("zh")
		self.ebook.add_author(self.author)
		self.ebook.set_cover(file_name="cover.jpg", content=self.image)
		if self.tags:
			for t in re.split(r" |,|，|。|\.|;｜；|\||｜|\\\|/|、", self.tags):
				self.ebook.add_metadata('DC', 'subject', t)
		if self.des:
			self.ebook.add_metadata('DC', 'description', self.des)

		# create add intro page
		intro = epub.EpubHtml(title="简介",file_name="intro.xhtml", lang="zh")
		intro.content = ("<h2>%s</h2><h3>作者：%s</h3><h3>内容标签：%s</h3><p>%s</p>" %
		                 (self.title, self.author, self.tags, self.des.replace("\n", "</p><p>")))
		self.ebook.toc.append(epub.Link("intro.xhtml", "简介", "intro"))
		self.ebook.add_item(intro)

		# create and add chapters
		indices = self.split_txt()
		chaps = self.get_chaps(indices)

		# add default NCX and Nav file
		self.ebook.add_item(epub.EpubNcx())
		self.ebook.add_item(epub.EpubNav())

		# define CSS style
		style = '''p {text-indent: 0.5em;}'''
		default_css = epub.EpubItem(
			uid="style_default",
			file_name="style/default.css",
			media_type="text/css",
			content=style)
		self.ebook.add_item(default_css)

		# basic spine
		self.ebook.spine = ["nav", intro, *chaps]

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
				self.info["tags"] = txt.group(3)
		element = soup.find(attrs=self.get_parser('des'))
		if element:
			self.info["des"] = "\n".join(element.stripped_strings)
		element = soup.find(self.get_parser('img'))
		if element:
			self.info["img"] = self.split_utl._replace(path=element.get("src")).geturl()

	def set_head(self):
		# Book title must be available. Try getting it by tags h1, title, only run this when failed parsing intro page
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
				self.info["tags"] = txt.group(3)

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
		self.set_head()
		if not self.get_info("title"):
			print(f"Download failed: getting no book title from {self.split_utl.geturl()}")
			return
		for x in ["title", "author", "tags", "des"]:
			self.info[x] = clean_txt(self.get_info(x))
		if not self.get_info("tags") and self.get_info("des"):
			temp = re.search('内容标签[:：](.*)', self.get_info("des"))
			if temp:
				self.info["tags"] = temp.group(1)

		if not self.get_info("pages"):
			print(f"Download failed: getting no pages from {self.split_utl.geturl()}")
			return
		text = ""
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
		EpubConverter(text, self.get_info('title'), self.get_info('author'), self.get_info("tags"),
		              self.get_info("des"), self.get_info('img'))
		return True


class LocalTxtToEpub:
	def __init__(self, file, image_url=None):
		self.file = file
		self.image_url = image_url

	def process(self):
		data = read_binary_file(self.file)
		if not data:
			return
		EpubConverter(data=data, title="", image_url=self.image_url).convert()
