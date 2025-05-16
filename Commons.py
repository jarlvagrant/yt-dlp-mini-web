import os

from flask import typing as ft, render_template, Response, request, jsonify, url_for, flash, send_from_directory
from flask.views import View

from Utils import ConfigIO, getSubfolders, getPossibleFolders


class UpdateConfig(View):
	methods = ['POST']
	def dispatch_request(self) -> ft.ResponseReturnValue:
		keys = request.form.get("key").split(" ")
		value = request.form.get("value")
		if len(keys) == 1:
			ConfigIO.set(keys[0], value)
		else:
			ConfigIO.set(keys[0], value, subkey=keys[1])
		print(f"Updating config: {keys} = {value}")
		return jsonify(code=200)


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
		code = 201
		if os.path.isdir(new_path):
			code = 200
			ConfigIO.set(dir_type, new_path)
		print(f"Updating directory: {dir_type} = {new_path}, code = {code}")
		return  jsonify(code=code)


class ListSubfolders(View):
	methods = ['POST']

	def dispatch_request(self) -> ft.ResponseReturnValue:
		cur_dir = request.form.get("cur_dir")
		print(cur_dir)
		folders = getPossibleFolders() + getSubfolders(cur_dir)
		print(folders)
		return jsonify(cur_dir=cur_dir, folders=folders)