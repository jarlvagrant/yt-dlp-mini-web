from flask import Flask, render_template
from flask.views import View
from werkzeug.serving import WSGIRequestHandler

from Commons import UpdateDir, UpdateConfig, ListSubfolders
from EbookSender import EBook, EbookUploads, EbookConverterTask, EbookCover, EbookCoverUrl, EbookEmail, \
	EbookUrls, EbookExtractorTask, EbookSyncInput, EbookDownload, EbookRemoveItem, EbookSyncOutput
from YdlWrapper import YoutubeDownloader, Progress, TaskMaker


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
	app.add_url_rule("/update_config", methods=['POST'], view_func=UpdateConfig.as_view("update_config"))
	app.add_url_rule("/list_subfolders", methods=['POST'], view_func=ListSubfolders.as_view("list_subfolders"))
	app.add_url_rule("/task_maker", methods=['POST'], view_func=TaskMaker.as_view("task_maker"))
	app.add_url_rule("/youtube", methods=['GET'], view_func=YoutubeDownloader.as_view("youtube"))
	app.add_url_rule("/progress", methods=['GET'], view_func=Progress.as_view("progress"))
	app.add_url_rule("/ebook", methods=['GET'], view_func=EBook.as_view("ebook"))
	app.add_url_rule("/ebk_urls", methods=['GET', 'POST'], view_func=EbookUrls.as_view("ebk_urls"))
	app.add_url_rule("/ebk_uploads", methods=['GET', 'POST'], view_func=EbookUploads.as_view("ebk_upload"))
	app.add_url_rule("/ebk_sync_input", methods=['POST'], view_func=EbookSyncInput.as_view("ebk_sync_input"))
	app.add_url_rule("/ebk_sync_output", methods=['POST'], view_func=EbookSyncOutput.as_view("ebk_sync_output"))
	app.add_url_rule("/ebk_cover", methods=['POST'], view_func=EbookCover.as_view("ebk_cover"))
	app.add_url_rule("/ebk_cover_url", methods=['POST'], view_func=EbookCoverUrl.as_view("ebk_cover_url"))
	app.add_url_rule("/ebk_convert_task", methods=['POST'], view_func=EbookConverterTask.as_view("ebk_convert_task"))
	app.add_url_rule("/ebk_extractor_task", methods=['POST'], view_func=EbookExtractorTask.as_view("ebk_extractor_task"))
	app.add_url_rule("/ebk_download", methods=['GET'], view_func=EbookDownload.as_view("ebk_download"))
	app.add_url_rule("/ebk_email", methods=['POST'], view_func=EbookEmail.as_view("ebk_email"))
	app.add_url_rule("/ebk_remove", methods=['POST'], view_func=EbookRemoveItem.as_view("ebk_remove"))
	app.run(debug=True, host='0.0.0.0', port=8008, request_handler=MyRequestHandler)


if __name__ == "__main__":
	main()
