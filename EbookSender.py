import os
import re
import threading
from pathlib import Path
from threading import Thread
from time import sleep
from urllib.parse import urlsplit, unquote

import chinese_converter
import requests
from bs4 import BeautifulSoup
from ebooklib import epub
from flask import typing as ft, render_template, Response, request, jsonify, flash, send_from_directory
from flask.views import View
from requests import HTTPError

from Utils import ConfigIO, UA, SendEmail, getInitialSubfolders, getInitialFolder, getTime


class LocalBookStatus:
	def __init__(self):
		self.status = {}

	def add(self, key):
		if not self.status.get(key):
			self.status[key] = {"intro": "", "image": "", "txt": "", "epub": "", "chapter": ""}

	def remove(self, key):
		self.status.pop(key, None)

	def get_value(self, key, sub_key):
		item = self.status.get(key)
		if not item:
			self.add(key)
			return self.get_value(key, sub_key)
		else:
			return item.get(sub_key)

	def set_value(self, key, sub_key, value):
		item = self.status.get(key)
		if not item:
			self.add(key)
			self.set_value(key, sub_key, value)
		else:
			item[sub_key] = value

	def get_value_if_key(self, key, sub_key):
		item = self.status.get(key)
		if item:
			return item.get(sub_key)
		return None

	def set_value_if_key(self, key, sub_key, value):
		item = self.status.get(key)
		if item:
			item[sub_key] = value

class UrlBookStatus(LocalBookStatus):
	def add(self, key):
		if not self.status.get(key):
			self.status[key] = {"content": "", "chapter": "", "thread": Thread(), "image": "", "txt": "", "epub": "",
			                    "error": "", "intro": "", "is_collapsed": ""}


local_book_dict = LocalBookStatus()

url_book_dict = UrlBookStatus()


class EBook(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		folder = getInitialFolder('ebook_dir')
		subfolders = getInitialSubfolders(folder)
		return render_template("ebk.html", ebook_dir=folder, folders=subfolders,
		                       recipient=ConfigIO.get("email", "to"))


class EbookSyncInput(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		key = request.form.get("key")
		sub_key = request.form.get("sub_key")
		value = request.form.get("value")
		local_book_dict.set_value_if_key(key, sub_key, value)
		url_book_dict.set_value_if_key(key, sub_key, value)
		print(f"Synced {key}: {sub_key} -> {value}")
		return jsonify(code=200)

class EbookSyncOutput(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		items = {}
		error = ""
		for k, v in url_book_dict.status.items():
			t = v.get('thread')
			if t and t.is_alive():
				items[k] = v.get('content')
			error += v.get('error')
		print(f"Extractor is working at {items.__str__()}")
		res = jsonify(code=200, items=items, error=error) if items else jsonify(code=200, error=error)
		return res

class EbookUploads(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		if request.method == "POST":
			path = ConfigIO.get("ebook_dir")
			if not os.path.isdir(path):
				flash("Invalid upload path: {path}")
			else:
				files = request.files.getlist("docs")
				for f in files:
					file_name = clean_txt(f.filename)
					file_path = os.path.join(path, file_name)
					f.save(file_path)
					local_book_dict.set_value(file_name, "txt", file_path)
					print(f"Uploaded file: {file_path}")
			return Response(status=200)
		return render_template("ebk_uploads.html", txt_files=local_book_dict.status)


class EbookDownload(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		file_path = request.args.get('file_path')
		print(f"Downloading request {file_path}")
		if not os.path.isfile(file_path):
			print(f"Invalid downloading path: {file_path}")
			return Response(status=404)

		directory = Path(file_path).parent
		path = Path(file_path).name
		return send_from_directory(directory, path=path)


busy_hosts = {str: threading.Event()}


class EbookUrls(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		if request.method == "POST":
			new_url = request.form.get('new_url')
			if new_url:
				url_book_dict.add(new_url)
		return render_template("ebk_urls.html", book_urls=url_book_dict.status)


class EbookExtractorTask(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		url = request.form.get("url")
		if not url:
			return jsonify(code=500, message="No url specified")
		intro = request.form.get("intro")
		method = request.form.get("method", "index")
		index_tag_k = request.form.get("index_tag_k")
		index_tag_v = request.form.get("index_tag_v")
		index_tag = {index_tag_k: index_tag_v} if index_tag_k and index_tag_v else {}
		next_tag = request.form.get("next_tag")
		content_tag_k = request.form.get("content_tag_k")
		content_tag_v = request.form.get("content_tag_v")
		content_tag = {content_tag_k: content_tag_v} if content_tag_k and content_tag_v else {}
		args = {"intro": clean_txt(intro), "method": method, "index_tag": index_tag, "next_tag": next_tag,
		        "content_tag": content_tag}

		print(f"{url}: {args.__str__()}")
		t = Thread(target=extractor_worker, args=(url, args))
		url_book_dict.set_value(url, "thread", t)
		t.start()
		return jsonify(code=200, message="Extracting {url}")


def extractor_worker(url, args):
	url_netloc = urlsplit(url).netloc
	print(f"Busy hosts: {busy_hosts.keys().__str__()}")
	if busy_hosts.get(url_netloc):
		print(f"Waiting for {url_netloc} to be free...")
		busy_hosts.get(url_netloc).wait()
	else:
		busy_hosts[url_netloc] = threading.Event()
	busy_hosts[url_netloc].clear()
	extractor = EbookWebExtractor(url, args)
	text = extractor.extract()
	content = text[0:2000] if len(text) > 2000 else text
	url_book_dict.set_value(url, "content", content)
	url_book_dict.set_value(url, "error", extractor.error)
	print(f"Host {url_netloc} freed")
	busy_hosts[url_netloc].set()

	# converter task doesn't need to be waiting for
	title, author, tags, des = get_meta_data(args.get("intro"), text)
	if not title:
		print(f"Can't save extracted content to file: failed to extract title")
		url_book_dict.set_value(url, "error", url_book_dict.get_value(url, "error") + "\nfailed to extract title")
		return
	txt_path = os.path.join(ConfigIO.get("ebook_dir"), title + ".txt")
	url_book_dict.set_value(url, "txt", txt_path)
	write_text_file(text, txt_path)
	image_path = url_book_dict.get_value(url, "image")

	print(f"Converting: title={title}, author={author}, tags={tags}, des={des}, image={image_path}")
	converter = EpubConverter(text, title, author, tags, des, image_path)
	output = converter.convert()
	url_book_dict.set_value(url, "epub", output)
	url_book_dict.set_value(url, "chapter", converter.info)


class EbookEmail(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		keys = request.form.getlist("keys[]")
		sub_key = request.form.get("sub_key")
		code = 200
		message = ""
		for key in keys:
			value = url_book_dict.get_value_if_key(key, sub_key) \
				if url_book_dict.get_value_if_key(key, sub_key) else local_book_dict.get_value_if_key(key, sub_key)
			if value:
				print(f"Sending email with attachment {value}")
				sender = SendEmail(value)
				code = 400 if not sender.send() else code
				message += sender.message + "\n"
		return jsonify(code=code, message=message)


class EbookConverterTask(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		key = request.form.get('key', '')
		intro = clean_txt(request.form.get('intro', ''))
		txt_path = local_book_dict.get_value(key, "txt")
		if not os.path.isfile(txt_path):
			return jsonify(code=500, messages="Input text file not found")

		data = clean_txt(read_binary_file(txt_path))
		title = clean_txt(Path(txt_path).stem)
		image_path = local_book_dict.get_value(key, "image")
		if not os.path.isfile(image_path):
			image_path = None
		_, author, tags, des = get_meta_data(intro, data)
		print(f"Converting: title={title}, author={author}, tags={tags}, des={des}, image={image_path}")
		converter = EpubConverter(data, clean_txt(title), clean_txt(author), clean_txt(tags), clean_txt(des),
		                          image_path)
		output = converter.convert()
		local_book_dict.set_value(key, "epub", output)
		local_book_dict.set_value(key, "chapter", converter.info)
		return jsonify(code=200, chapter=converter.info, epub=output)


class EbookCover(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		key = request.form.get('title')
		file = request.files.get('image')
		if key and file:
			image_name = file.filename
			image_path = os.path.join(ConfigIO.get("ebook_dir"), image_name)
			image = file.read()
			print(f"Save image: {image_name} to {image_path}")
			if image:
				with open(image_path, "wb") as f:
					f.write(image)
				local_book_dict.set_value_if_key(key, "image", image_path)
				url_book_dict.set_value_if_key(key, "image", image_path)
				return Response(status=200)
		return Response(status=500)


class EbookCoverUrl(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		key = request.form.get('title')
		url = request.form.get('img_url')
		if key and url:
			image = get_image(url)
			image_name = Path(url).stem + ".jpg"
			image_path = os.path.join(ConfigIO.get("ebook_dir"), image_name)
			print(f"Save image: {url} to {image_path}")
			if image:
				with open(image_path, "wb") as f:
					f.write(image)
				local_book_dict.set_value_if_key(key, "image", image_path)
				url_book_dict.set_value_if_key(key, "image", image_path)
				return jsonify(code=200)
		return jsonify(code=500)


class EbookRemoveItem(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		key = request.form.get('key')
		to_all = request.form.get('all')
		if to_all:
			url_book_dict.status.clear()
			local_book_dict.status.clear()
		else:
			url_book_dict.remove(key)
			local_book_dict.remove(key)
		return jsonify(code=200)


def get_meta_data(intro, data):
	content = intro if intro else data
	title, author, tags = "", "", ""
	seg = re.search(r"(?s)[.]?([^\n《》「」『』【】\/]*).?\n?作者[：:]([^\n》」』】\(]*)", content)
	if seg:
		title = seg.group(1)
		author = seg.group(2)
	if not title:
		for line in content.split():
			if line and not line.strip().startswith("http"):
				title = line
				break
	if not tags:
		seg = re.search('内容标签[:：](.*)', content)
	if seg:
		tags = seg.group(1)
	return title.strip(), author.strip(), tags, intro


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
		self.info = ""
		self.ebook = epub.EpubBook()

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
		file_path = os.path.join(self.path, self.title + ".epub")
		epub.write_epub(file_path, self.ebook, {})
		print(f"Success: {self.title} converting done. number of chapters: {len(indices)}")
		return file_path


class EbookWebExtractor:
	def __init__(self, url, args: dict):
		self.split_utl = urlsplit(url)
		self.message = ""
		self.error = ""
		self.content = ""
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

	def update(self):
		# only need this to show progress on webpage
		url = self.split_utl.geturl()
		url_book_dict.set_value_if_key(url, "message", self.message)
		url_book_dict.set_value_if_key(url, "error", self.error)
		url_book_dict.set_value_if_key(url, "content", self.content)

	def extract(self):
		method = self.info.get("method", "index")
		if method == "index":
			self.set_message(f"Fetching page urls from index page: {self.split_utl.geturl()}")
			self.set_pages_index()
			text = self.extract_index()
		elif method == "next_tag":
			self.set_message(f"Fetching page urls from first page: {self.split_utl.geturl()}")
			text = self.extract_traverse()
		else:
			self.set_message(f"Please input extracting method - index or next(page by page): {self.split_utl.geturl()}")
			text = ""
		text = clean_txt(text)
		text = re.sub(self.info.get('watermark', ""), '', text)
		if len(text) < 10000:
			self.set_error(f"Suspected download failure. Article is too short: {len(text)}")
		else:
			self.set_message(f"Download Success. Word count: {len(text)}")
		return text

	def extract_index(self):
		if not self.info.get("pages"):
			self.set_error(f"Failed to get pages from index page {self.split_utl.geturl()}")
			return ""
		self.set_message(f"Extracting {len(self.info.get("pages"))} pages from {self.split_utl.geturl()}")
		text = self.info.get("intro") + "\n" if self.info.get("intro") else ""
		attr = self.info.get("content_tag") if self.info.get("content_tag") else {
			"id": "text"}  # input content_tag or use id=text
		for idx, page in enumerate(self.info.get("pages")):
			soup = extractHtmlSoup(page)
			if not soup:
				self.set_error(f"Failed to download page {page}\n")
				break
			element = soup.find(attrs=attr)
			if element:
				temp = "\n".join(element.stripped_strings)
				text += temp
				temp = f"{idx}/{len(self.info.get("pages"))}\n{temp}"
				self.content = (temp[0:50] if len(temp) > 50 else temp) + "......"
			else:
				self.set_error(f"Failed to extract page {page}, wrong content tag: {attr}")
				break
			self.update()
			sleep(0.5)  # to avoid 429 Client Error: Too Many Requests
		return text

	def extract_traverse(self):
		text = self.info.get("intro") + "\n" if self.info.get("intro") else ""
		n = self.info.get("next_tag") if self.info.get("next_tag") else "下一页"
		attr = self.info.get("content_tag") if self.info.get("content_tag") else {
			"id": "text"}  # input content_tag or use id=text
		url = self.split_utl.geturl()
		page = 0
		while True:
			soup = extractHtmlSoup(url)
			if not soup:
				self.set_error(f"Failed to download page {url}\n")
				break
			text_element = soup.find(attrs=attr)
			if text_element:
				temp = "\n".join(text_element.stripped_strings)
				text += temp
				temp = f"{page}/unknown\n{temp}"
				self.content = (temp[0:50] if len(temp) > 50 else temp) + "......"
			else:
				self.set_error(f"Failed to extract page {url}, wrong content tag: {attr}")
				break
			n_element = soup.find(string=n)
			if not n_element:
				self.set_message(f"Last page {url}\n")
				break
			href = n_element.parent.get("href")
			if not href:
				self.set_message(f"Last page {url}\n")
				break
			if not self.split_utl.netloc in href:  # not all href contain the host location
				href = self.split_utl.netloc + href
			url = href
			self.update()
		return text

	def set_pages_index(self):
		soup = extractHtmlSoup(self.split_utl.geturl())
		if not soup:
			return
		hrefs = []
		pages = set()
		attr = self.info.get("index_tag")
		if attr:  # input contains index tag
			element = soup.find(attrs=attr)
			if element:
				pages = element.find_all("a")
		else:  # there are many unordered list in html, I bet the longest list is the page list
			uls = soup.find_all("ul")
			for ul in uls:
				a = ul.find_all("a")
				if a and len(a) > len(pages):
					pages = a
		for p in pages:
			h = p.get("href")
			if h:
				if not self.split_utl.netloc in h:  # not all href contain the host location
					h = self.split_utl.netloc + h
				hrefs.append(h)
		self.info["pages"] = hrefs

	def set_message(self, message):
		print(message)
		self.message += message + "\n"

	def set_error(self, message):
		self.set_message(message)
		self.error += message + "\n"
