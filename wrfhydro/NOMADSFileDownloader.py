########################################################################
#
# This script downloads files from NCEP's NOMADS data site
# using throttling to limit the number of requests per minute
# made to the data server, in response to new usage limits
# being enforced. It has the following features:
#
# - Sleeps until the next minute when the maximum number of requests has been reached
# - Alternates between downloading small and large files to minimize sleep time
#   (i.e. to avoid downloading many small files in rapid succession and hitting the
#    request limit too early in the minute)
# - Download all dates or just a single date
# - Configure which forecast cycles to download and which file types to download for each
# - Only downloads new or incomplete files from the server
# - Preserves file modification times
#
########################################################################

import runpy
import urllib.request
import urllib.error
import socket
import os
import logging as log
from datetime import datetime
import time
from optparse import OptionParser
import signal
import re
import traceback
import ssl
import codecs

ssl._create_default_https_context = ssl._create_unverified_context


def exit_on_sigterm(a,b):
    log.info("SIGTERM received. Exiting")
    exit(0)


# capture SIGTERM so we can log it
signal.signal(signal.SIGTERM, exit_on_sigterm)

# Global constants used for notification emails
APP_NAME = "NWMFileDownloader.py"
MAIL_APP = "/usr/bin/Mail"

# Global constants. Modify these if the directory listing
# format changes on the server
INDEX_FILE_REGEX = "<a href=\"(.+?)\".+?<\/a>\s+([\w|\d|-]+ [\d|:]+)\s+([\w|\d|\-|\.]+)"
INDEX_FILE_DATE_FORMAT = "%d-%b-%Y %H:%M"

# Global variables used by all functions
download_times = []
total_num_files = 0
total_num_requests = 0
total_timeouts = 0
total_errors = 0
app_starttime = datetime.now()

params = None
options = None

default_params = """#
# This is the default parameter file for NWMFileDownloader.py
# All parameters must be defined for the parameter file to be
# valid.
#
# The parameter file follows all python coding syntax rules,
# (and in fact is executed as python code.)
#
##############################################################


# ------------ Data Input ---------------
# Root URL of the data on the server.
root_url = "http://nomads.ncep.noaa.gov/pub/data/nccf/com/nwm/prod"

# URL (relative to root_url) of the dated folder. Use __DATE__ as a placeholder for the date.
# Wildcards (*) may be used to match other directory levels, but each level of the dated folder's
# parents (up to root_url) MUST be specified with a '/'
date_url = "nwm.__DATE__"

# Date format used for the URLs representation of __DATE__. See strftime for available format characters
url_date_format = "%Y%m%d"

# URL (relative to root_url) of the forecast cycle folder. Use __FORECAST_CYCLE__ as a placeholder for the forecast
# cycle. Wildcards (*) may be used to match other directory levels, but each level of the forecast cycle folder's
# parents (up to root_url) MUST be specified with a '/'
forecast_cycle_url = "*/__FORECAST_CYCLE__"

# Forecast cycles to download. Each forecast cycle is a dict containing the name used in the input URL, and
# a list of file patterns to download for each.
# To download all forecast cycles use '*' for the name.
# To download all files for a forecast cycle use ['*'] for the file patterns list
forecast_cycles = [
    {'name': 'analysis_assim', 'file_patterns': ['*reservoir*','*land*']},
    {'name': 'short_range', 'file_patterns': ['*']}
]

# ------------ Data Output ---------------
# Local directory structure for writing output files. Use __DATE__ and __FORECAST_CYCLE__ placeholders
output_dir = "/d1/data/__DATE__/__FORECAST_CYCLE__"

# ------------ Request Settings ----------
# The maximum number of requests that will be made to the http server
# per minute. This includes both file requests and directory listings
max_requests_per_minute = 50

# Timeout for requests and file downloads. This is a timeout for stalled, not slow, connections.
# Set to None None to use the system's default timeout
timeout = 20

# Maximum number of timeouts that will be tolerated before application terminates.
max_timeouts = 2

# Maximum number of other errors that will be tolerated before application terminates.
max_errors = 2

# List of email addresses to notify in case of too many timeouts or other errors
emails = ['myself@me.com']

# Limit notification emails to one per this many minutes to avoid getting 'spammed' by recurring errors
notification_min_minutes = 1440
"""


class objectview(object):
    """
    Utility class used for converting param dict to an object

    """
    def __init__(self, d):
        self.__dict__ = d


def load_params(paramfile):
    """
    Load parameters from a file into a global parameter object
    :param paramfile: The path to the param file
    """
    global params

    try:
        params = objectview(runpy.run_path(paramfile))

        # construct urls and regex patterns from the supplied parameters.
        params.root_url = params.root_url.rstrip("/")
        params.date_url = params.root_url + "/" + params.date_url.rstrip("/").replace("*", ".*?")
        params.forecast_cycle_url = params.root_url + "/" + params.forecast_cycle_url.rstrip("/").replace("*", ".*?")

        if params.timeout is not None:
           socket.setdefaulttimeout(params.timeout)

    except Exception as e:
        print("Error loading parameter file: %s" % e )


def load_options():
    """
    Load command line arguments
    :return:
    """
    global options

    parser = OptionParser(usage="%prog [options]")
    parser.add_option("--print-params", dest="print_params", default=False, action="store_true",
                      help="Print default parameter file and exit")
    parser.add_option("-p", "--params", dest="paramfile", default=None, help="Path to parameter file")
    parser.add_option("-d", "--date", dest="date", default=None, help="Download only data from this date. Use YYYYMMDD")
    parser.add_option("-l", "--latest", dest="latest", default=False, action="store_true", help="Download latest forecast cycle closest to now")
    parser.add_option("--debug", dest="debug", default=False, action="store_true", help="Turn on debugging messages")

    (options, args) = parser.parse_args()

    # set logging based on --debug option
    log_level = log.DEBUG if options.debug else log.INFO
    log.basicConfig(format="%(levelname)s, %(asctime)s %(message)s", level=log_level)

    # if a date is supplied, create a Date object
    if options.date is not None:
        try:
            options.date = datetime.strptime(options.date, "%Y%m%d")
        except:
            print("Error: Invalid time format")
            options = None


def throttle():
    """
    Sleep until next minute and reset counts if the maximum number of requests
    has been reached for this minite
    :return:
    """
    global params, download_times

    now = datetime.now()

    # purge times longer than a minute ago from our request times list
    while len(download_times) > 0 and (now-download_times[0]).total_seconds() >= 60:
        download_times.remove(download_times[0])

    # if the number of requests left in the list exceeds our threshold, sleep a bit
    if len(download_times) > params.max_requests_per_minute:
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


def notify_timeout_and_exit(url, info):
    """
    Prepare email message when too many timeouts have occurred
    :param url:  The URL where the timeout occurred
    :param info: Additional info to add to email
    """
    msg = "Hello,\n\n" \
        + "The number of timeouts encountered exceeded the threshold of %s.\n" % params.max_timeouts \
        + "  Program run time: %s\n" % app_starttime.strftime("%Y-%m-%d %H:%M:%S") \
        + "  Last operation timed out at %s\n" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") \
        + "  URL: %s\n" % url \
        + "  Info: %s\n" % info

    notify_and_exit("Too many timeouts", msg)


def notify_error_and_exit(url, info):
    """
    Prepare email message when too many errors have occurred
    :param url:  The URL where the error occurred
    :param info: Additional info to add to email
    """
    msg = "Hello,\n\n" \
          + "The number of errors exceeded the threshold of %s.\n" % params.max_errors \
          + "  Program run time: %s\n" % app_starttime.strftime("%Y-%m-%d %H:%M:%S") \
          + "  Error occurred at %s\n" % datetime.now().strftime("%Y-%m-%d %H:%M:%S") \
          + "  URL: %s\n" % url \
          + "  Info: %s\n" % info

    notify_and_exit("Too many errors", msg)


def notify_and_exit(subject, message):
    """
    Send notification emails and exit
    :param subject: The email subject
    :param message: The email message
    """
    global params

    try:
        send_email = True
        if os.path.isfile(params.last_email_file):
            f = open(params.last_email_file, "r")
            dt = f.read()
            f.close()

            minutes = (int(datetime.now().strftime("%s")) - int(dt)) / 60
            if minutes < params.notification_min_minutes:
                send_email = False

        if send_email:
            log.debug("Sending notification emails.")

            for email in params.emails:
                f = os.popen("%s -s '%s: %s' %s" % (MAIL_APP, APP_NAME, subject, email), "w")
                f.write(message)
                f.close()

            f = open(params.last_email_file, "w")
            f.write(datetime.now().strftime("%s"))
            f.close()

    except Exception as e:
        log.error("Unable to send notification emails: %s" % e)

    log.error("Done, with errors")
    exit(1)


def get_file(url, output, size,modified):
    """
    Retrieve a file from the server and preserve server file modification times
    :param url: The URL of the file on the server
    :param output: The path of the file to write locally
    :param size: The expected size of the file in bytes, for logging
    :return: True on success, false on error
    """
    global total_num_files, total_timeouts, total_errors, params

    throttle() # wait to make request if we need to slow down
    downloadedStr = "Downloading"
    if modified is not None:
        downloadedStr = "Redownloading modified"
    log.debug("%s file '%s' of size %d bytes to '%s'" % (downloadedStr, url, size, output))

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
        log.error("Error downloading file '%s': %s. Deleting local file to try again later." % (url, e))
        if os.path.isfile(output):
            try:
                os.remove(output)
            except Exception as e1:
                log.error("Could not delete file! %s" % e1)

        if (isinstance(e, urllib.error.URLError) and isinstance(e.reason, socket.timeout)) \
                or isinstance(e, socket.timeout):
            total_timeouts += 1
            if total_timeouts > params.max_timeouts:
                notify_timeout_and_exit(url, e)
        else:
            total_errors += 1
            if total_errors > params.max_errors:
                notify_error_and_exit(url,e)

        return False


def read_index(url):
    """
    Download and parse the HTML index file into a list of files and directories. This may need to be
    modified if the listing format changes on the server.
    :param url: The URL of the directory we want to list
    :return: A list of dicts representing each file or directory name, file size, and modification time
    """
    global total_timeouts, total_errors, params

    # make sure we slow down if needed, even for directory listings which are still considered
    # a request
    throttle()

    log.debug("Getting index of %s" % url)

    try:
        # get the HTML. Assumes UTF-8 format
        increment_request_count()
        htmldata = urllib.request.urlopen(url, timeout=params.timeout).read()
        if type(htmldata) is not str:
            lines = codecs.decode(htmldata, 'utf-8',errors='ignore')
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

        if (isinstance(e, urllib.error.URLError) and isinstance(e.reason, socket.timeout)) \
                or isinstance(e, socket.timeout):
            total_timeouts += 1
            if total_timeouts > params.max_timeouts:
                notify_timeout_and_exit(url, e)
        else:
            total_errors += 1
            if total_errors > params.max_errors:
                notify_error_and_exit(url, e)

        return False


def download_files(url):
    """
    Recursively download configured files and directories
    :param url: The URL of the directory to process
    :return: True on success, false on error
    """
    global options, params

    files = read_index(url)
    files_to_download = []

    if (not files):
        return False

    # loop through each file or directory
    for f in files:
        # is it a directory?
        if f['name'][-1] == "/":
            path = url.rstrip("/") + "/" + f['name'].rstrip("/")

            # make sure it's our desired date
            if path.count("/") == params.date_url.count("/"):
                fmt = options.date.strftime(params.url_date_format) if options.date is not None else ".+?"
                dt = params.date_url.replace("__DATE__", fmt) + "$"
                if re.search(dt, path) is None:
                    continue

            # make sure it's our desired forecast cycle
            if path.count("/") == params.forecast_cycle_url.count("/"):
                pattern = params.forecast_cycle_url.replace("__FORECAST_CYCLE__", "(.+?)") + "$"
                fcst = re.search(pattern, path)
                if fcst is None:
                    continue

                fcst = fcst.groups()[0]
                match = False
                for fc in params.forecast_cycles:
                    if fc['name'] == "*" or fc['name'] == fcst:
                        match = True
                        break
                if not match:
                    continue

            # recursive call to download directory contents
            download_files(path)
            continue

        # it's a file. Compile a list of desired files, then sort them so we can alternate
        # between downloading large and small files
        else:
            path = url.rstrip("/") + "/" + f['name']

            # get the forecast cycle and the date from the url
            pattern = params.forecast_cycle_url.replace("__FORECAST_CYCLE__", "(.+?)" + "$")
            fcst = re.search(pattern, path).groups()[0].split("/")[0]
            pattern = params.date_url.replace("__DATE__", "(.+?)" + "$")
            dt = re.search(pattern, path).groups()[0].split("/")[0]

            # match the declared forecast cycle with its configuration in the paramfile
            fcycle = None
            for fc in params.forecast_cycles:
                if fc['name'] == '*' or fc['name'] == fcst:
                    fcycle = fc
                    break

            if fcycle is None:
                continue

            # make sure it matches the pattern of one of our desired file types
            match = False
            if fcycle['file_patterns'] == '*' or fcycle['file_patterns'][0] == "*":
                match = True
            else:
                for fp in fcycle['file_patterns']:
                    if re.match(fp.replace("*",".*"), f['name']):
                        match = True
            if not match:
                continue

            # create the output path
            outdir = params.output_dir.replace("__DATE__", dt).replace("__FORECAST_CYCLE__", fcst)
            outfile = outdir + "/" + f['name']

            # see if we've already downloaded the file
            modified = None
            if os.path.isfile(outfile):
                modified = os.stat(outfile).st_mtime
                if f['modified'].timestamp() <= modified:
                    continue

            files_to_download.append({'inurl': path, 'outdir': outdir, 'outfile': outfile, 'size': f['size'], 'modified': modified})

    if len(files_to_download) == 0:
        return True

    # sort files so they are a mix of small and large files, so hopefully we can maximize our requests per minute
    files = mix_file_sizes(files_to_download)

    # download each file, in order
    for f in files:
        # create parent directories if needed
        if not os.path.isdir(f['outdir']):
            os.makedirs(f['outdir'])

        get_file(f['inurl'], f['outfile'],f['size'],f['modified'])

    return True


def mix_file_sizes(files):
    """
    Create a new list of files sorted so that the app alternates between downloading small and large files
    :param files: A list of file dicts containing file size
    :return:
    """
    sorted_files = []

    find_min = True
    # Alternate between popping the smallest and largest file off the list, and add it to our
    # sorted list
    while len(files) > 0:
        g = files[0]
        for f in files:
            if (find_min and f['size'] < g['size']) or (not find_min and f['size'] > g['size']):
                g = f
        files.remove(g)
        sorted_files.append(g)
        find_min = not find_min

    return sorted_files


def run():
    """
    Run the application
    :return: True on success, false on error
    """
    global params, options, default_params

    load_options()
    if not options:
        return False

    if options.print_params:
        print(default_params)
        exit(0)

    if not options.paramfile:
        print( "Error: Must supply a parameter file!")
        return False

    load_params(options.paramfile)
    if not params:
        return False

    log.info("Downloading files from %s" % params.root_url)
    success = download_files(params.root_url)

    log.info("Total number of requests: %d" % total_num_requests)
    log.info("Total number of files downloaded: %d" % total_num_files)
    log.info("Done.")

    # if we made it here, enable email notifications if we encounter an error the next time
    try:
        if os.path.isfile(params.last_email_file):
            os.remove(params.last_email_file)
    except Exception as e:
        log.error("Unable to remove last notification file.")

    return success


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
        notify_and_exit("Uncaught Exception", "An error occurred: %s" % ex)
