from flask import Flask, render_template
from flask.views import View
from werkzeug.serving import WSGIRequestHandler

from EbookSender import EBook, EbookInputs, EbookUpload, EbookConvert, EbookCover, EbookCoverUrl
from YdlWrapper import UpdateDir, YoutubeDownloader, Progress, TaskMaker


class Index(View):
	def dispatch_request(self):
		return render_template('index.html')

class MyRequestHandler(WSGIRequestHandler):
	def log_request(self, code='-', size='-'):
		pass

def main():
	app = Flask(__name__)
	app.secret_key = 'mimamuahilachocobooooo'
	app.add_url_rule("/", view_func=Index.as_view("index"))
	app.add_url_rule("/update_dir", methods=['POST'], view_func=UpdateDir.as_view("update_dir"))
	app.add_url_rule("/task_maker", methods=['POST'], view_func=TaskMaker.as_view("task_maker"))
	app.add_url_rule("/youtube", view_func=YoutubeDownloader.as_view("youtube"))
	app.add_url_rule("/progress", view_func=Progress.as_view("progress"))
	app.add_url_rule("/ebook", view_func=EBook.as_view("ebook"))
	app.add_url_rule("/ebk_inputs", view_func=EbookInputs.as_view("ebk_inputs"))
	app.add_url_rule("/ebk_upload", view_func=EbookUpload.as_view("ebk_upload"))
	app.add_url_rule("/ebk_cover", view_func=EbookCover.as_view("ebk_cover"))
	app.add_url_rule("/ebk_cover_url", view_func=EbookCoverUrl.as_view("ebk_cover_url"))
	app.add_url_rule("/ebk_convert", view_func=EbookConvert.as_view("ebk_convert"))
	app.run(debug=True, host='0.0.0.0', port=8008, request_handler=MyRequestHandler)


if __name__ == "__main__":
	main()
