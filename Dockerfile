# Use an official Python runtime as the base image
FROM python:3-slim

RUN apt-get update && apt-get -y install git curl xz-utils

RUN apt-get -y install libfreetype6-dev libharfbuzz-dev libfribidi-dev meson gtk-doc-tools

RUN curl -L -o ffmpeg.tar.xz https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz

RUN tar -xf ffmpeg.tar.xz -C /opt

RUN mv /opt/ffmpeg-master-latest-linux64-gpl /opt/ffmpeg

ENV PATH="$PATH:/opt/ffmpeg/bin"

RUN rm ffmpeg.tar.xz

# Set the working directory in the container
WORKDIR /app

RUN git clone https://github.com/jarlvagrant/yld_webwrapper.git .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 5000 available to the world outside this container
EXPOSE 8008

# Define environment variable
#ENV FLASK_APP=app.py

# Run the application
#CMD ["flask", "run", "--host=0.0.0.0"]
CMD ["sh", "-c", "git restore .; git clean -f; git pull; pip install --upgrade pip; pip install --no-cache-dir -r requirements.txt; python WebTools.py"]

