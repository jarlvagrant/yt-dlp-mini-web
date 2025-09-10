import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template
from flask.views import View
from werkzeug.serving import WSGIRequestHandler

from Commons import UpdateDir, UpdateConfig, ListSubfolders
from Utils import log_path, log_file
from YdlWrapper import YoutubeDownloader, Progress, TaskMaker, FetchFormats


class Index(View):
	def dispatch_request(self):
		return render_template('index.html')

class MyRequestHandler(WSGIRequestHandler):
	def log_request(self, code='-', size='-'):
		pass

class HTTPFilter(logging.Filter):
		def filter(self, record: logging.LogRecord) -> bool:
			if record.name == "EbookSender":
				return True
			return False

def init_logging():
	if not os.path.isdir(log_path):
		os.mkdir(log_path)
	# http_handler: logging.Handler = HTTPHandler("localhost:8008", "/log", method="GET")
	# http_handler.addFilter(HTTPFilter())
	logging.basicConfig(
		handlers=[RotatingFileHandler(os.path.join(log_path, log_file), maxBytes=100000, backupCount=10),
		          # http_handler,
		          logging.StreamHandler(sys.stdout)],
		format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
		datefmt='%Y-%m-%d %H:%M:%S',
		level=logging.DEBUG)


def main():
	init_logging()

	app = Flask(__name__)
	app.secret_key = 'mimamuahilachocobooooo'
	app.add_url_rule("/", view_func=Index.as_view("index"))
	app.add_url_rule("/update_dir", methods=['POST'], view_func=UpdateDir.as_view("update_dir"))
	app.add_url_rule("/update_config", methods=['POST'], view_func=UpdateConfig.as_view("update_config"))
	app.add_url_rule("/list_subfolders", methods=['POST'], view_func=ListSubfolders.as_view("list_subfolders"))
	app.add_url_rule("/task_maker", methods=['POST'], view_func=TaskMaker.as_view("task_maker"))
	app.add_url_rule("/fetch_formats", methods=['POST'], view_func=FetchFormats.as_view("fetch_formats"))
	app.add_url_rule("/youtube", methods=['GET'], view_func=YoutubeDownloader.as_view("youtube"))
	app.add_url_rule("/progress", methods=['GET'], view_func=Progress.as_view("progress"))

	app.run(debug=True, host='0.0.0.0', port=8008, request_handler=MyRequestHandler)


if __name__ == "__main__":
	main()
