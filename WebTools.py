from flask import Flask

from EbookSender import EBook
from YdlWrapper import Index, UpdateDir, YoutubeDownloader, ProgressData


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
