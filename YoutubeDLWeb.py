import json
import os

import yt_dlp
from flask import Flask, typing as ft, request, render_template, jsonify, Response
from flask.views import View

started_progress = {}


def readJson(file):
	with open(file, 'r') as f:
		content = json.load(f)
	return content


def writeJson(file, content):
	with open(file, 'w', encoding='utf-8') as f:
		json.dump(content, f, ensure_ascii=False, indent=4, )


config = readJson("config.json")
output_dir = config.get("output_dir", ".")


class Index(View):
	def dispatch_request(self):
		return render_template('base.html', output_dir=output_dir)


class UpdateDir(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		path = request.form.get("dir")
		print(path)
		is_dir = os.path.isdir(path)
		response = "f"
		if is_dir:
			response = "t"
			config["output_dir"] = path
			writeJson("config.json", config)
		return Response(response=response, status=200)


class YoutubeDownloader(View):
	outputTypes = {'video': 'mp4/bestvideo/best', 'audio': 'm4a/bestaudio/best'}

	def dispatch_request(self) -> ft.ResponseReturnValue:
		return render_template("toolbox.html", output_dir=output_dir)


class Downloader:
	def __init__(self, uuid, url, format):
		self.uuid = uuid
		self.url = url
		self.format = format
		self.cur = 0
		self.error = None
		self.title = ""

	def setTitle(self):
		with yt_dlp.YoutubeDL({}) as ydl:
			info_dict = ydl.extract_info(self.url, download=False)
			self.title = info_dict.get('title', '')
			ydl.close()

	def my_hook(self, d):
		try:
			self.cur = str(d["_percent_str"]).strip().replace("%", "")
			print("\nCurrent progress %s percent." % self.cur)
		except:
			print("\nUnknown progress percentage...")
		if d['status'] == 'finished':
			self.cur = 100

	def download_video(self):
		global output_dir
		ext = 'mp4/bestvideo/best' if self.format == "true" else 'm4a/bestaudio/best'
		print("requested format " + ext)
		ydl_opts = {
			"outtmpl": output_dir + '/%(title)s.%(ext)s',
			# this is where you can edit how you'd like the filenames to be formatted
			'progress_hooks': [self.my_hook],
			'format': ext,
		}
		with yt_dlp.YoutubeDL(ydl_opts) as ydl:
			self.error = ydl.download(self.url)
			ydl.close()


class ProgressData(View):
	def dispatch_request(self, uuid) -> ft.ResponseReturnValue:
		global started_progress
		if started_progress.get(uuid):
			downloader = started_progress[uuid]
		else:
			print("create new downloader " + uuid)
			downloader = Downloader(uuid, request.args.get("url"), request.args.get("format"))
			started_progress[uuid] = downloader
			try:
				downloader.setTitle()
				downloader.download_video()
			except Exception as ex:
				downloader.error = ex.__str__()
		if downloader.error or downloader.cur == 100:
			started_progress.pop(uuid, None)
		data = jsonify(label=downloader.title, cur=downloader.cur, error=downloader.error)
		print(data.get_json())
		return data


def main():
	app = Flask(__name__)
	app.secret_key = 'mimamuahilachocobooooo'
	app.add_url_rule("/", view_func=Index.as_view("index"))
	app.add_url_rule("/update_dir", view_func=UpdateDir.as_view("update_dir"))
	app.add_url_rule("/youtube", view_func=YoutubeDownloader.as_view("youtube"))
	app.add_url_rule("/progress_data/<uuid>", view_func=ProgressData.as_view("progress_data"))
	app.run(debug=True, host='0.0.0.0', port=8008)


if __name__ == "__main__":
	main()
