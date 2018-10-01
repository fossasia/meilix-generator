# Set the base image
FROM alpine:latest
RUN apk add --no-cache py-crypto \
                       py-tornado \
                       py-mysqldb \
                       python && \
                       python -m ensurepip && \
                       rm -r /usr/lib/python*/ensurepip && \
                       pip install --upgrade pip setuptools && \
                       rm -r /root/.cache


# File Author / Maintainer
MAINTAINER Xeon Zolt

#creating dir for Meilix Generator
RUN mkdir /app
WORKDIR /app

# installing required apps
## installing required python modules
ADD requirements.txt /app/
RUN pip install -r requirements.txt

#adding Meilix Generator code
COPY . /app/

# starting the app
ENTRYPOINT ["gunicorn", "-b", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-"]
CMD ["app:app"]
