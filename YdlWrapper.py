import os

import yt_dlp
from flask import typing as ft, request, render_template, jsonify, Response
from flask.views import View

from Utils import ConfigIO

started_progress = {}


class UpdateDir(View):
	"""
	Using a POST method to retrieve the javascript id, value pair for one of the
	archive path(video, audio, book...)
	Response is the validated retrieved path. If this path is not a valid directory,
	send the previous path as response.
	"""
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		new_path = request.form.get("dir")
		dir_type = request.form.get("id")
		old_path = ConfigIO.get(dir_type)
		response = old_path
		if os.path.isdir(new_path):
			response = new_path
			ConfigIO.set(dir_type, new_path)
			print("Updating directory: %s = %s" % (dir_type, new_path))
		return Response(response=response, status=200)


output_formats = {
	'video': "bestvideo[ext=mp4][height<=720][vcodec!~=av01]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
	'audio': 'bestaudio[ext=m4a][acodec!~=opus]/best'}


class YoutubeDownloader(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		return render_template("ydl.html", video_dir=ConfigIO.get("video_dir"), audio_dir=ConfigIO.get("audio_dir"))


class Downloader:
	def __init__(self, uuid, url, ext, output_dir, start=0, end=0):
		self.uuid = uuid
		self.urls = [url]
		self.ext = ext
		self.output_dir = output_dir
		self.start = min(start, end) - 1
		self.end = max(start, end)
		self.cur = 0
		self.error = None
		self.title = f"Fetching info from {url}..."
		self.completed = 0
		self.status = ""

	def set_info(self):
		with yt_dlp.YoutubeDL({'extract_flat': "in_playlist"}) as ydl:
			info_dict = ydl.extract_info(self.urls[0], download=False)
			self.title = info_dict.get('title', '')
			# playlist_count = info_dict.get('playlist_count', 0)
			entries = info_dict.get("entries", None)
			if entries:
				self.urls = [entry.get("url", None) for entry in entries]
				if self.start < 0 or self.start >= len(self.urls):
					self.start = 0
				if self.end <= 0 or self.end > len(self.urls):
					self.end = len(self.urls)
				self.urls = self.urls[self.start:self.end]
			ydl.close()

	# need work!
	def my_hook(self, d):
		self.status = d['_default_template']
		self.cur = round(d["_percent"], 1)
		print("\nCurrent progress %s percent." % self.cur)

	def my_postprocessor_hook(self, d):
		self.status = d['_default_template']

	def download_video(self):
		print("requested format %s; output directory %s." % (self.ext, self.output_dir))
		ydl_opts = {
			"outtmpl": self.output_dir + "/%(title)s.%(ext)s",
			'progress_hooks': [self.my_hook],
			'postprocessor_hooks': [self.my_postprocessor_hook],
			'format': self.ext,
		}
		with yt_dlp.YoutubeDL(ydl_opts) as ydl:
			for url in self.urls:
				if url:
					self.error = ydl.download(url)
					self.completed += 1
			self.status = "completed"
			ydl.close()


class ProgressData(View):
	def dispatch_request(self, uuid) -> ft.ResponseReturnValue:
		# verify output directory
		resolution = request.args.get("resolution", "720", type=str)
		if request.args.get("format") == "true":
			ext = output_formats.get("video", "").replace("720", resolution)
			output_dir = ConfigIO.get("video_dir")
		else:
			ext = output_formats.get("audio", "")
			output_dir = ConfigIO.get("audio_dir")
		if not os.path.isdir(output_dir):
			data = jsonify(label="Initialization: ", cur="0", error=f"{output_dir} is not a valid directory!")
			return data

		global started_progress
		if started_progress.get(uuid):
			downloader = started_progress[uuid]
		else:
			print("create new downloader " + uuid)
			downloader = Downloader(uuid, request.args.get("url"), ext, output_dir,
			                        request.args.get("start", 0, type=int), request.args.get("end", 0, type=int))
			started_progress[uuid] = downloader
			try:
				downloader.set_info()
				downloader.download_video()
			except Exception as ex:
				downloader.error = ex.__str__()
		if downloader.error or downloader.cur == 100:
			started_progress.pop(uuid, None)
		label = f"{downloader.title} ({downloader.completed}/{len(downloader.urls)})" if downloader.title else ""
		data = jsonify(label=label, status=downloader.status, cur=downloader.cur, error=downloader.error)
		print(data.get_json())
		return data
