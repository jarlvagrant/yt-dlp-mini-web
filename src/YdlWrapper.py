import logging
import os
import re
import time
from multiprocessing import Process, Queue

import yt_dlp
from flask import typing as ft, request, render_template, jsonify
from flask.views import View

from Utils import ConfigIO, getInitialFolder, getSubfolders

logger = logging.getLogger(__name__)

tasks = []

output_formats = { 'video': "bestvideo[ext=mp4][height<=720][vcodec!~=av01]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
                   'audio': 'bestaudio[ext=m4a][acodec!~=opus]/best'}
video_args = ['format_id', 'format', 'fps', 'protocol', 'vcodec', 'ext']
audio_args = ['format_id', 'format', 'protocol', 'ext']

class Task:
	def __init__(self, url, ext, selector_args, output_dir, playlist_items):
		self.url = url
		self.ext = ext
		self.selector_args = selector_args
		self.output_dir = output_dir
		self.playlist_items = playlist_items
		self.status = {"title": "unknown", # video/audio title
		               "info": "initializing", # progress data-label
		               "error": "", # show error button
		               "width": "width:0%;", # progress bar width
		               "state": "start", # state start, stop, complete
		               "switch": "stop", # button text - switch task to start -> stop, stop -> start
		               "color": "background-color: #7cc4ff;" # progress bar background-color: slategray/#7cc4ff
		               }
		self.queue = Queue()
		self.process = Process(target=Downloader, args=(self.url, self.ext, self.selector_args, self.output_dir, self.playlist_items, self.queue))
		self.process.start()

	def restart(self):
		if not self.process or not self.process.is_alive():
			self.process = Process(target=Downloader, args=(self.url, self.ext, self.selector_args, self.output_dir, self.playlist_items, self.queue))
			self.status['state'] = 'start'
			self.status['switch'] = "stop"
			self.status['color'] = "background-color: #7cc4ff;"
			self.process.start()
			return True
		return False

	def stop(self):
		if self.process and self.process.is_alive():
			self.process.terminate()
			time.sleep(0.1)
		if self.process and not self.process.is_alive():
			self.status['state'] = 'stop'
			self.status['switch'] = 'start'
			self.status['color'] = "background-color: slategray;"
			return True
		return False

def parse_arg(input_string, arg):
	match = re.search(rf"{arg}([^,]*)", input_string)
	if match:
		logger.info(match.group(1))
		return match.group(1)
	return ""

class TaskMaker(View):
	def __init__(self):
		self.url = request.form.get("url", "")
		self.action = request.form.get("action", "")
		self.playlist_items = request.form.get("playlist_items", "")
		self.selector_args = {}

		output_type = request.form.get("output_type", "video")
		resolution = request.form.get("resolution", "720", type=str)
		quality = request.form.get("quality", "best", type=str)
		video_format_id = parse_arg(resolution, "format_id=")
		audio_format_id = parse_arg(quality, "format_id=")

		if audio_format_id:
			self.selector_args['audio_format_id'] = audio_format_id
		if output_type == "video" and video_format_id:
			self.selector_args['video_format_id'] = video_format_id

		self.ext = output_formats.get("video", "").replace("720", resolution) if resolution in ['1080', '720', '480'] else ""
		self.output_dir = ConfigIO.get("video_dir")
		if output_type == "audio":
			self.ext = output_formats.get("audio", "").replace("best", quality) if quality in['best', 'worst'] else ""
			self.output_dir = ConfigIO.get("audio_dir")

		self.code = 200
		self.message = "success"

	def dispatch_request(self) -> ft.ResponseReturnValue:
		if self.action == "start":
			# to start a new downloading process, verify path, create a downloader, and add Task to task list.
			if not os.path.isdir(self.output_dir):
				self.code = 201 # invalid path
			else:
				task = self.get_task()
				if task:
					state = task.status.get('state', '')
					if state == "start":
						self.code = 202 # ongoing task
						self.message = "Process already running: " + task.status.__str__()
					elif state == "complete":
						self.code = 203 # completed task
						self.message = "Completed task: " + task.status.__str__()
					elif state == 'stop':
						if not task.restart():
							self.code = 204 # unknown task to restart downloading
							self.message = "Unknown task: " + task.status.__str__()
					else:
						self.code = 205 # unknown state
						self.message = "Unknown state: " + task.status.__str__()
				else:
					# start downloading
					logger.info(f"Downloading {self.url}: ext={self.ext} selector_args={self.selector_args} output={self.output_dir} playlist_items{self.playlist_items}" )
					tasks.append(Task(self.url, self.ext, self.selector_args, self.output_dir, self.playlist_items))
		elif self.action == "stop":
			# to stop an existing downloads
			self.stop_task(self.get_task())
		elif self.action == "stop_all":
			# to stop all ongoing downloads
			for task in tasks:
				self.stop_task(task)
		elif self.action == "clear":
			# clear downloading list, remove completed or stopped tasks from the list
			for task in tasks[:]: # make a copy of the list to avoid skippint items
				if task.status['state'] != 'start':
					tasks.remove(task)
		logger.info(f"Task {self.action}: url={self.url} code={self.code} message={self.message}")
		return jsonify(code=self.code, message=self.message)

	def get_task(self) -> Task | None:
		for t in tasks:
			if t.url == self.url:
				return t
		return None

	def stop_task(self, task: Task):
		# terminate process, remove process and queue from prog_dict.
		if not task.stop():
			self.code = 206 # Unknown task/process, or process is not alive
			self.message += "Task not terminated: " + task.status.__str__() + "\n"


class Progress(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		prog_dict = {}
		for task in tasks:
			if task.queue:
				while not task.queue.empty():
					k, v = task.queue.get_nowait()
					if k == "info":
						if not v.startswith("[download]"):
							logger.info(v)
						task.status[k] = v
					elif k == "warning":
						logger.warning(v)
						task.status["error"] = task.status["error"] + v
					elif k == "error":
						logger.error(v)
						task.status["error"] = task.status["error"] + v
					else:
						task.status[k] = v
			prog_dict[task.url] = task.status
		# print(prog_dict.__str__())
		return render_template("progress.html", prog_dict=prog_dict)


class FetchFormats(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		url = request.form.get("url", "")
		videos = []
		audios = []
		try:
			ydl = yt_dlp.YoutubeDL({'extract_flat': True})
			formats = ydl.extract_info(url, download=False).get('formats')
			for f in formats:
				if f['vcodec'] != 'none':
					videos.append([f"{arg}={f[arg]}" for arg in video_args])
				elif 'acodec' not in f or f['acodec'] != 'none':
					audios.append([f"{arg}={f[arg]}" for arg in audio_args])
			ydl.close()
		except Exception as e:
			logger.error(e)
		logger.info("Available video formats: " + videos.__str__())
		logger.info("Available audio formats: " + audios.__str__())
		return jsonify(videos=videos, audios=audios)


class YoutubeDownloader(View):
	def dispatch_request(self) -> ft.ResponseReturnValue:
		video_dir = getInitialFolder("video_dir")
		video_subfolders = getSubfolders(video_dir)
		audio_dir = getInitialFolder("audio_dir")
		audio_subfolders = getSubfolders(audio_dir)
		return render_template("ydl.html", video_dir=video_dir, audio_dir=audio_dir,
		                       video_folders=video_subfolders, audio_folders=audio_subfolders)


class Downloader:
	def __init__(self, url, ext, selector_args, output_dir, playlist_items, queue):
		self.url = url
		self.ext = ext
		self.selector_args = selector_args
		self.output_dir = output_dir
		self.playlist_items = playlist_items
		self.queue = queue
		self.title = ""
		self.download_video()

	def download_video(self):
		# with yt_dlp.YoutubeDL({'extract_flat': "in_playlist"}) as ydl:
		# 	info_dict = ydl.extract_info(self.url, download=False)
		# 	self.title = info_dict.get('title', '')
		# 	self.queue.put(('title', self.title))
		# 	ydl.close()

		def my_hook(d):
			if not self.title and d['info_dict'] and d['info_dict']['title']:
				self.title = d['info_dict']['title']
				self.queue.put(('title', self.title))

		def format_selector(ctx):
			# formats are already sorted worst to best
			formats = ctx.get('formats')[::-1]

			best_video = next(f for f in formats if f['format_id'] == self.selector_args.get('video_format_id'))
			best_audio = next(f for f in formats if f['format_id'] == self.selector_args.get('audio_format_id'))
			logger.info(best_video)
			logger.info(best_audio)

			yield {
				'format_id': f'{best_video["format_id"]}+{best_audio["format_id"]}',
				'ext': best_video['ext'],
				'requested_formats': [best_video, best_audio],
				# Must be + separated list of protocols
				'protocol': f'{best_video["protocol"]}+{best_audio["protocol"]}'
			}

		ydl_opts = {
			"outtmpl": self.output_dir + "/%(title)s.%(ext)s",
			"playlist_items" : self.playlist_items,
			'logger': MyLogger(self.queue),
			'format': self.ext,
			'progress_hooks': [my_hook],
		}

		if self.selector_args:
			ydl_opts['format'] = format_selector

		try:
			ydl = yt_dlp.YoutubeDL(ydl_opts)
			ydl.download(self.url)
			ydl.close()
			self.queue.put(('info', f"Download completed: {self.title}"))
			self.queue.put(('width', f"width:100%"))
			self.queue.put(('state', 'complete'))
		except Exception as e:
			self.queue.put(('info', f"Download failed: {self.title}"))
			self.queue.put(('info', e.__str__()))


class MyLogger:
	def __init__(self, queue):
		self.queue = queue

	def debug(self, msg):
		# For compatibility with youtube-dl, both debug and info are passed into debug
		# You can distinguish them by the prefix '[debug] '
		if msg.startswith('[debug] '):
			pass
		else:
			self.info(msg)

	def info(self, msg):
		self.queue.put(('info', msg))
		temp = re.search(r"\d+\.?\d*%", msg)
		if temp:
			self.queue.put(('width', f"width:{temp.group()}"))

	def warning(self, msg):
		self.queue.put(('warning', msg))

	def error(self, msg):
		self.queue.put(('error', msg))
