from flask import Flask, render_template
from flask.views import View

from EbookSender import EBook
from YdlWrapper import UpdateDir, YoutubeDownloader, ProgressData


class Index(View):
	def dispatch_request(self):
		return render_template('index.html')


def main():
	app = Flask(__name__)
	app.secret_key = 'mimamuahilachocobooooo'
	app.add_url_rule("/", view_func=Index.as_view("index"))
	app.add_url_rule("/update_dir", view_func=UpdateDir.as_view("update_dir"))
	app.add_url_rule("/youtube", view_func=YoutubeDownloader.as_view("youtube"))
	app.add_url_rule("/progress_data/<uuid>", view_func=ProgressData.as_view("progress_data"))
	app.add_url_rule("/ebook", view_func=EBook.as_view("ebook"))
	app.run(debug=True, host='0.0.0.0', port=8008)


if __name__ == "__main__":
	main()
