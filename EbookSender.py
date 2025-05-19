import os
import re
from pathlib import Path
from time import sleep
from urllib.parse import urlsplit, unquote

import chinese_converter
import requests
from bs4 import BeautifulSoup
from ebooklib import epub
from flask import typing as ft, render_template, Response, request, jsonify, url_for, flash, send_from_directory
from flask.views import View
from requests import HTTPError
from werkzeug.utils import redirect

from Utils import ConfigIO, UA, SendEmail, getInitialSubfolders, getInitialFolder

book_dict = {}


class EBook(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		folder = getInitialFolder('ebook_dir')
		subfolders = getInitialSubfolders(folder)
		return render_template("ebk.html", ebook_dir=folder, folders=subfolders,
		                       recipient=ConfigIO.get("email", "to"))


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
		file = request.files.get('image')
		if file:
			print(f"Save image: {file.filename} to {title}")
			image = file.read()
			if image:
				with open(os.path.join(ConfigIO.get("ebook_dir"), title), "wb") as f:
					f.write(image)
					return Response(status=200)
		return Response(status=500)


class EbookCoverUrl(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		title = request.form.get('title', 'unknown') + ".jpg"
		url = request.form.get('img_url')
		if url:
			print(f"Save image: {url} to {title}")
			image = get_image(url)
			if image:
				with open(os.path.join(ConfigIO.get("ebook_dir"), title), "wb") as f:
					f.write(image)
				return jsonify(code=200)
		return jsonify(code=500)


class EbookLink(View):
	methods = ['GET']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		print(f"Uploading request {request.url}")
		filename = request.args.get('filename')
		return send_from_directory(ConfigIO.get("ebook_dir"), path=filename)


class EbookEmail(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		items = request.form.getlist('files[]')
		print(f"Sending email with attachment {items}")
		for item in items:
			SendEmail(os.path.join(ConfigIO.get("ebook_dir"), item), filename=item).send()
		return jsonify(code=200)


class EbookConvert(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		file_name = request.form.get('file', '')
		title = request.form.get('title', '')
		author = request.form.get('author', '')
		tags = request.form.get('tags', '')
		des = request.form.get('des', '')
		image_name = request.form.get('image', '') + ".jpg"
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
		converter = EpubConverter(data, clean_txt(title), clean_txt(author), clean_txt(tags), clean_txt(des),
		                          image_path)
		output = converter.convert()
		return jsonify(code=200, info=converter.info, output=output)


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
chap_regex_list = [
	r"(?m)^[\s\r\n\.☆、—-]*第[0123456789一二三四五六七八九十零〇百千两]+[章回部节集卷][\s\r\n\.☆、—-].{0,30}",  # 第一章 飞雪连天
	r"(?m)^.{0,10}第[0123456789一二三四五六七八九十零〇百千两]+[章回部节集卷].{0,30}",  # 1. 第一章 飞雪连天
	r"(?m)^[\s\r\n\.☆、—-]*\d+[\s\r\n\.☆、—-].{0,30}",  # 1. 飞雪连天
	r"(?m)^.{0,10}\d+.{0,30}",  # 正文 1. 飞雪连天
	r"(?m)^[\s\r\n\.☆、—-]*[第章集卷][0123456789一二三四五六七八九十零〇百千两]+[\s\r\n\.☆、—-].{0,30}",  # ☆ 卷一 飞雪连天
	r"(?m)^.{0,10}[第章集卷][0123456789一二三四五六七八九十零〇百千两]+[\s\r\n\.☆、—-].{0,30}",  # ☆一。 卷一 飞雪连天
	r"(?m)^[\s\r\n\.]*[☆、—-].{0,30}"]  # ☆ 飞雪连天


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
		except HTTPError as ex:
			print(f"Error: Downloading {url} with {ex}")
			if ex.response.status_code == 429:
				sleep(5)
			retry -= 1
		except Exception as ex:
			print(f"Error: Downloading {url} with {ex}")
			UA.renew()
			retry -= 1
	return None


def extractHtmlImage(url: str):
	image = None
	response = extractHtml(url)
	if response and response.status_code == 200:
		image = response.content
	return image


def extractHtmlText(url: str, cookies=None):
	text = ""
	response = extractHtml(url, cookies)
	if response and response.status_code == 200:
		response.encoding = response.apparent_encoding
		text = unquote(response.text, response.encoding)
	return text


def extractHtmlSoup(url: str, cookies=None):
	soup = None
	text = extractHtmlText(url, cookies)
	if text:
		soup = BeautifulSoup(text, 'html5lib')
	return soup


class EpubConverter:
	def __init__(self, data, title="", author="", tags="", des="", image_url=None):
		self.data = data
		self.path = ConfigIO.get("ebook_dir")
		self.title = title if title else ""
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
		start = 0
		end = len(self.data)
		indices = []
		while end - start > 8000:
			diff = -1
			for regex in chap_regex_list:
				found = re.search(regex, self.data[start: start + 8000])
				if found:
					diff = found.start()
					indices.append(start + diff)
					start += found.end()
					break
			if diff == -1:  # no chap with known regex found smaller than 8000 words
				diff = self.data[start:start + 8000].rfind("\n")  # find the last occurrence of line breaker
				if diff == -1:
					start += 8000
				else:
					start += diff
				indices.append(start)
		indices.append(end)
		print(indices)
		return indices

	def convert(self):
		if not self.data:
			print("Error: the resource txt file has no content")
			return ""
		if not self.title:
			print("Error: can not convert txt file with no title")
			return ""
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
		intro = epub.EpubHtml(title="简介", file_name="intro.xhtml", lang="zh")
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
		return self.title + ".epub"


class EbookWebExtractor:
	def __init__(self, url, args: dict):
		self.split_utl = urlsplit(url)
		self.message = ""
		self.args = args
		self.info = {}
		self.setup()

	def setup(self):
		for p in ConfigIO.get("web_parsers"):  # known network location from config
			if p.get("base", "") == self.split_utl.netloc:
				for key, value in p.items():
					self.info[key] = value
		for k, v in self.args.items():  # input info manually, override parsed info
			self.info[k] = v
		self.set_message(f"Gathered info: {self.info.__str__()}")

	def set_pages_indexed(self):
		soup = extractHtmlSoup(self.split_utl.geturl())
		if not soup:
			return
		hrefs = []
		pages = set()
		attr = self.info.get("indexed")
		if attr: # input contains indexed
			element = soup.find(attrs=attr)
			if element:
				pages = element.find_all("a")
		else: # there are many unordered list in html, I bet the longest list is the page list
			uls = soup.find_all("ul")
			for ul in uls:
				a = ul.find_all("a")
				if a and len(a) > len(pages):
					pages = a
		for p in pages:
			h = p.get("href")
			if h:
				if not self.split_utl.netloc in h: # not all href contain the host location
					h = self.split_utl.netloc + h
				hrefs.append(h)
		self.info["pages"] = hrefs

	def extract(self):
		if self.info.get("indexed"):
			self.set_message(f"Fetching page urls from index page: {self.split_utl.geturl()}")
			self.set_pages_indexed()
			return self.extract_index()
		elif self.info.get("next"):
			self.set_message(f"Fetching page urls from first page: {self.split_utl.geturl()}")
			return self.extract_traverse()
		else:
			self.set_message(f"Please input extracting method - index or next(page by page): {self.split_utl.geturl()}")
			return ""

	def extract_index(self):
		if not self.info.get("pages"):
			self.set_message(f"Failed to get pages from index page {self.split_utl.geturl()}")
			return ""
		self.set_message(f"Extracting {len(self.info.get("pages"))} pages from {self.split_utl.geturl()}")
		text = self.info.get("intro") + "\n" if self.info.get("intro") else ""
		attr = self.info.get("content_tag") if self.info.get("content_tag") else {"id": "nr1"} # input content_tag or use id=nr1
		for page in self.info.get("pages"):
			soup = extractHtmlSoup(page)
			temp = f"Failed to download page {page}\n"
			if soup:
				element = soup.find(attrs=attr)
				if element:
					temp = "\n".join(element.stripped_strings)
				else:
					temp = f"Failed to extract page {page}, wrong content tag: {attr}"
			text += temp
			sleep(0.5) # to avoid 429 Client Error: Too Many Requests
		text = clean_txt(text)
		text = re.sub(self.info.get('watermark', ""), '', text)
		if len(text) < 10000:
			self.set_message(f"Suspected download failure. Article is too short: {len(text)}")
		else:
			self.set_message(f"Download Success. Word count: {len(text)}")
		return text

	def extract_traverse(self):
		text = self.info.get("intro") + "\n" if self.info.get("intro") else ""
		n = self.info.get("next") if self.info.get("next") else "下一页"
		attr = self.info.get("content_tag") if self.info.get("content_tag") else {"id": "nr1"} # input content_tag or use id=nr1
		url = self.split_utl.geturl()
		while True:
			soup = extractHtmlSoup(url)
			if not soup:
				self.set_message(f"Failed to download page {url}\n")
				break
			text_element = soup.find(attrs=attr)
			if text_element:
				temp = "\n".join(text_element.stripped_strings)
			else:
				temp = f"Failed to extract page {url}, wrong content tag: {attr}"
			text += temp
			n_element = soup.find(string=n)
			if  not n_element:
				self.set_message(f"Last page {url}\n")
				break
			href = n_element.parent.get("href")
			if not href:
				self.set_message(f"Last page {url}\n")
				break
			if not self.split_utl.netloc in href: # not all href contain the host location
				href = self.split_utl.netloc + href
			url = href
		return text

	def set_message(self, message):
		print(message)
		self.message += message + "\n"