import urllib.request
import urllib.error
import socket
import os
import logging as log
from datetime import datetime, timedelta
import traceback
import time
import signal
import re
import ssl
import codecs

log.basicConfig(format="%(levelname)s, %(asctime)s %(message)s", level=log.DEBUG)

ssl._create_default_https_context = ssl._create_unverified_context

# Global constants. Modify these if the directory listing
# format changes on the server
INDEX_FILE_REGEX = "<a href=\"(.+?)\".+?<\/a>\s+([\w|\d|-]+ [\d|:]+)\s+([\w|\d|\-|\.]+)"
INDEX_FILE_DATE_FORMAT = "%d-%b-%Y %H:%M"

URL = "http://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"

MAX_REQUESTS_PER_MINUTE = 50
TIMEOUT = 60

# Global variables used by all functions
download_times = []
total_num_files = 0
total_num_requests = 0
total_timeouts = 0
total_errors = 0
app_starttime = datetime.utcnow()

OUTDIR = os.environ['FORCING_INPUTDIR']
DATE = os.environ['FORCING_DATE']
LENGTH = os.environ['LENGTH_HRS']


def exit_on_sigterm(a,b):
    log.info("SIGTERM received. Exiting")
    exit(1)

# capture SIGTERM so we can log it
signal.signal(signal.SIGTERM, exit_on_sigterm)


def throttle():
    """
    Sleep until next minute and reset counts if the maximum number of requests
    has been reached for this minite
    :return:
    """
    global download_times

    now = datetime.now()

    # purge times longer than a minute ago from our request times list
    while len(download_times) > 0 and (now-download_times[0]).total_seconds() >= 60:
        download_times.remove(download_times[0])

    # if the number of requests left in the list exceeds our threshold, sleep a bit
    if len(download_times) > MAX_REQUESTS_PER_MINUTE:
        sleep_secs = int(60 - (now - download_times[0]).total_seconds())
        if sleep_secs <= 0:
            sleep_secs = 1
        log.debug("Throttle activated after %d requests since %s. Sleeping %s seconds." %
              (len(download_times) - 1, download_times[0].strftime("%Y-%m-%d %H:%M:%S"), sleep_secs))

        time.sleep(sleep_secs)
        throttle()


def increment_request_count():
    """
    Increment global request counters
    :return:
    """
    global total_num_requests, download_times

    total_num_requests += 1
    download_times.append(datetime.now())


def get_file(url, output, size):
    """
    Retrieve a file from the server and preserve server file modification times
    :param url: The URL of the file on the server
    :param output: The path of the file to write locally
    :param size: The expected size of the file in bytes, for logging
    :return: True on success, false on error
    """
    global total_num_files, total_timeouts, total_errors

    throttle()  # wait to make request if we need to slow down
    log.debug("Downloading file '%s' of size %d bytes to '%s'" % (url, size, output))

    try:
        increment_request_count()
        start = datetime.now()
        ret = urllib.request.urlretrieve(url, output)

        log.debug("Download took %d seconds" % (datetime.now() - start).total_seconds())

        # set file times locally
        access_time = datetime.strptime(ret[1]['Date'], "%a, %d %b %Y %H:%M:%S %Z").strftime("%s")
        modified_time = datetime.strptime(ret[1]['Last-Modified'], "%a, %d %b %Y %H:%M:%S %Z").strftime("%s")
        os.utime(output, (int(access_time), int(modified_time)))

        total_num_files += 1

        return True

    except Exception as e:
        log.error("Error downloading file '%s': %s" % (url,e))
        return False


def log_and_exit(msg, e):
    log.error("%s: %s" % (msg, e))
    log.error("Done, with errors")
    exit(1)


def read_index(url):
    """
    Download and parse the HTML index file into a list of files and directories. This may need to be
    modified if the listing format changes on the server.
    :param url: The URL of the directory we want to list
    :return: A list of dicts representing each file or directory name, file size, and modification time
    """
    global total_timeouts, total_errors

    # make sure we slow down if needed, even for directory listings which are still considered
    # a request
    throttle()

    log.debug("Getting index of %s" % url)

    try:
        # get the HTML. Assumes UTF-8 format
        increment_request_count()
        htmldata = urllib.request.urlopen(url, timeout=TIMEOUT).read()
        if type(htmldata) is not str:
            lines = codecs.decode(htmldata, 'utf-8', errors='ignore')
        else:
            lines = htmldata

        lines = lines.split("\n")

        files = []
        # parse each line
        for l in lines:
            m = re.search(INDEX_FILE_REGEX, l)
            if not m:
                continue

            m = m.groups()
            name = m[0]
            # convert file modified string into a Date object
            modified = datetime.strptime(m[1], INDEX_FILE_DATE_FORMAT)

            # convert file size given in kilobytes (K), megabytes (M), or gigabytes (G)
            # into number of bytes
            size = m[2]
            mult = size[-1]
            if mult == "K":
                mult = 1024
            elif mult == "M":
                mult = 1024 * 1024
            elif mult == "G":
                mult = 1024 * 1024 * 1024
            else:
                mult = None

            if mult:
                size = int(float(size[:-1]) * mult)
            else:
                try:
                    size = int(size)
                except:
                    size = 0

            files.append({'name': name, 'modified': modified, 'size': size})

        return files

    except Exception as e:
        log.error("Error reading index of '%s': %s" % (url, e))
        return False


def get_data(url):
    got_all = False

    files = read_index(url)
    if not files:
        return False

    for f in files:
        match = re.search("^gfs.t\d\dz.sfluxgrbf(\d+).grib2$", f['name'])
        if not match:
            continue

        hour = int(match.groups()[0])
        if hour > int(LENGTH):
            continue

        outfile = "%s/%s" % (OUTDIR, f['name'])
        if os.path.isfile(outfile):
            continue

        success = get_file("%s/%s" % (url, f['name']), "%s/%s" % (OUTDIR, f['name']), f['size'])    

        if not success:
            got_all = False
            continue

        if hour == int(LENGTH):
            got_all = True

    return got_all


def run():
    log.debug("Looking for files for time %s" % DATE )
    tm = DATE[0:8]
    hr = DATE[-2:]

    got_all_files = False
    # loop until our data becomes available
    while True:
        dirs = read_index(URL)
        daydir = None
        
        if dirs:
            log.debug("Looking for files for %s" % DATE)
            for d in dirs:
                try:
                    dt = datetime.strptime(d['name'], "gfs.%Y%m%d/")
                except:
                    continue
                if dt.strftime("%Y%m%d") != tm:
                    continue
                daydir = d['name']
                break

        if not daydir:
            log.debug("Files not found. Sleeping 5 minutes")
            time.sleep(300)
            continue

        # found the day directory, now find the cycle directory
        dirs = read_index("%s/%s" % (URL, daydir))
        hourdir = None
        
        if dirs:
            for d in dirs:
                d = d['name'].replace("/","")
                if d == hr:
                    hourdir = d
                    break

        if not hourdir:
            log.debug("Files not found. Sleeping 5 minutes")
            time.sleep(300)
            continue

        dir = "%s/%s/%s/atmos" % (URL, daydir, hourdir)
        success = get_data(dir)

        if success:
            log.debug("Downloaded all files. Exiting")
            return True    

        log.debug("Waiting for more files")
        time.sleep(300)


if __name__ == "__main__":
    try:
        success = run()
        if not success:
            exit(1)

        exit(0)
    except KeyboardInterrupt:
        print("Interrupted. Program exiting")
        exit(1)
    except Exception as e:
        ex = "%s\n%s" % (e, traceback.format_exc())
        log.error("Uncaught exception: %s" % ex)
        log_and_exit("An error occurred", ex)
