import os
import re
from pathlib import Path

import chinese_converter
import requests
from ebooklib import epub
from flask import typing as ft, render_template, Response, request
from flask.views import View

from Utils import ConfigIO


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
	txt = re.sub(r'\n{5,}', '\n\n\n\n', txt)
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


def get_image(image_file):
	image = None
	if image_file:
		if os.path.isfile(image_file):
			with open(image_file, 'rb') as f:
				image = f.read()
		elif image_file.startswith("http") or image_file.startswith("ftp"):
			try:
				image = requests.get(image_file, headers={
					'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0'}).content
			except Exception as ex:
				print(f"failed downloading image {ex}")
	return image


class EpubConverter:
	def __init__(self, data, input_file, title="", author="", image_file=None):
		self.data = read(data, input_file)
		self.path = ConfigIO.get("ebook_dir")
		self.title = title if title else Path(input_file).stem
		self.author = author
		self.image = get_image(image_file)
		self.ebook = epub.EpubBook()
		write(self.data, os.path.join(self.path, self.title + ".txt"))

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

		self.data = clean_txt(read(self.data))
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
		print(f"converting done. number of chapters: {len(indices) - 1}")
