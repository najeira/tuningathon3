# -*- coding: utf-8 -*-

import sys
import threading
import httplib
import urllib
import time
import uuid
from subprocess import Popen, PIPE, STDOUT
try:
  from cStringIO import StringIO
except ImportError:
  from StringIO import StringIO

SCORE_HOST = '127.0.0.1'
URL_TXT = '/home/ec2-user/url.txt'
HTTP_LOAD = '/home/ec2-user/http_load'
DEFAULT_SECONDS = 10
DEFAULT_CONCURRENCY = 10
PATH_GET = '/blojsom/blog/default/2012/03/23/test'
PATH_POST = '/blojsom/blog/default/2012/03/23/test'
PARAMS_POST = {
  'comment': 'y',
  'entry_id': '1',
  'permalink': 'test',
  'redirect_to': PATH_GET,
  'author': 'test',
  'authorEmail': '',
  'authorURL': '',
  'submit': 'Comment',
}


class CheckerThread(object):
  
  def __init__(self, host, seconds):
    self._host = host
    self._seconds = float(seconds)
    self._cond = threading.Condition(threading.Lock())
    self._thread = threading.Thread(target=self._run)
    self._thread.daemon = True
    self._value = None
  
  def _run(self):
    try:
      start_time = time.time()
      comment = ''
      num_ok = 0
      num_err = 0
      num_post = 0
      loop = 0
      while True:
        
        if loop % 2:
          if self.get_page(comment):
            num_ok += 1
          else:
            num_err += 1
          #check elapsed
          elapsed = time.time() - start_time
          if elapsed > self._seconds:
            break
        else:
          comment = self.post_comment()
          num_post += 1
        
        loop += 1
      
      score = float(num_post) / elapsed * 10
      percent = float(num_ok) / float(num_ok + num_err)
      value = (score, percent, num_post)
      
    except Exception, e:
      import traceback
      print traceback.format_exc()
      value = e
      
    finally:
      self._cond.acquire()
      try:
        self._value = value
        self._cond.notify()
      finally:
        self._cond.release()
  
  def get_page(self, comment):
    try:
      ret = http_get(self._host, PATH_GET)
    except Exception:
      return False
    if comment not in ret:
      return False
    return True
  
  def post_comment(self):
    comment = uuid.uuid4().hex
    params = {'commentText': comment}
    params.update(PARAMS_POST)
    try:
      http_post(self._host, PATH_POST, params, timeout=60)
    except Exception:
      pass
    return comment
  
  def start(self):
    self._thread.start()
  
  def wait(self, timeout=None):
    self._cond.acquire()
    try:
      if self._value is None:
        self._cond.wait(timeout or 60)
    finally:
      self._cond.release()
  
  def get(self, timeout=None):
    self.wait(timeout)
    if isinstance(self._value, tuple):
      return self._value
    raise self._value


def http_get(host, path, timeout=60):
  headers = {'User-Agent': 'http_load 12mar2006', 'Connection': 'close'}
  conn = httplib.HTTPConnection(host, timeout=timeout)
  try:
    conn.request("GET", path, headers=headers)
    r = conn.getresponse()
    status = r.status
    if 200 != status:
      return None
    return r.read() #OK
  finally:
    conn.close()


def http_post(host, path, params, timeout=60):
  headers = {'User-Agent': 'http_load 12mar2006', 'Connection': 'close',
    'Content-type': 'application/x-www-form-urlencoded'}
  params_encoded = urllib.urlencode(params)
  conn = httplib.HTTPConnection(host, timeout=timeout)
  try:
    conn.request("POST", path, params_encoded, headers=headers)
    r = conn.getresponse()
    status = r.status
    if 200 != status:
      return None
    return r.read() #OK
  finally:
    conn.close()
 

def run_bench(host, seconds, concurrency):
  
  #http://localhost/foo/bar
  if host.startswith('http://'):
    host, _ = host.split('//', 1)[1].split('/', 1)
  
  #create URL_TXT for http_load
  init_url_txt(host)
  
  #start CheckerThread
  checker = CheckerThread(host, seconds)
  checker.start()
  
  #start http_load
  rets = run_http_load(concurrency, seconds)
  
  #parse result of http_load
  score_http_load = parse_http_load_result(rets, seconds)
  
  #get result of CheckerThread
  score_checker, percent, num_post = checker.get()
  score_total = score_http_load + score_checker
  score = score_total * percent * percent
  
  print 'Score: %.3f (get=%.3f, comment=%.3f(%d), check=%.3f)' % (
    score, score_http_load, score_checker, num_post, percent)
  
  #post score to score server
  if 10 == concurrency:
    send_score(score)
  
  return score


def init_url_txt(host):
  #create URL_TXT for http_load
  f = open(URL_TXT, 'wb')
  try:
    f.write('http://%s%s' % (host, PATH_GET))
  finally:
    f.close()


def run_http_load(concurrency, seconds):
  #http_load -parallel 9 -seconds 10 url.txt
  args = [HTTP_LOAD, '-parallel', str(concurrency - 1), '-seconds', str(seconds), URL_TXT]
  p = Popen(args, stdout=PIPE, stderr=STDOUT)
  
  #wait http_load
  try:
    rets = []
    for line in p.stdout.readlines():
      line = line.rstrip()
      if line.endswith('byte count wrong'):
        continue #ignore ... ?
      rets.append(line)
      print line
    p.wait()
  except:
    p.terminate()
    raise
  
  return rets


def parse_http_load_result(lines, seconds):
  assert lines[0].split(',')[-1].endswith('seconds')
  if lines[5] == 'HTTP response codes:':
    statuses = lines[6:]
  elif lines[6] == 'HTTP response codes:':
    statuses = lines[7:]
  else:
    raise ValueError()
  fetches = int(lines[0].split(',')[0].split(' ')[0])
  num_ok, num_err = parse_status_lines(statuses)
  #assert num_ok + num_err == fetches
  #succeeds_percent = num_ok / fetches
  #assert 1.0 >= succeeds_percent
  elapsed = float(lines[0].split(' in ')[-1].split(' ')[0])
  return float(num_ok) / elapsed


def test_parse_http_load_result():
  ret = parse_http_load_result("""\
1485 fetches, 1 max parallel, 2.02792e+07 bytes, in 3.10000 seconds
13656 mean bytes/connection
494.978 fetches/sec, 6.75942e+06 bytes/sec
msecs/connect: 0.143007 mean, 0.23 max, 0.072 min
msecs/first-response: 1.87696 mean, 19.596 max, 1.644 min
HTTP response codes:
  code 200 -- 1485""".splitlines(), 3)
  assert 1437 == int(ret), ret
  
  ret = parse_http_load_result("""\
1485 fetches, 1 max parallel, 2.02792e+07 bytes, in 3.00013 seconds
13656 mean bytes/connection
494.978 fetches/sec, 6.75942e+06 bytes/sec
msecs/connect: 0.143007 mean, 0.23 max, 0.072 min
msecs/first-response: 1.87696 mean, 19.596 max, 1.644 min
HTTP response codes:
  code 200 -- 1400
  code 503 -- 85""".splitlines(), 3)
  assert 1399 == int(ret), ret
  
  ret = parse_http_load_result("""\
135 fetches, 9 max parallel, 3.1411e+06 bytes, in 10.0001 seconds
23267.4 mean bytes/connection
13.4998 fetches/sec, 314105 bytes/sec
msecs/connect: 0.17497 mean, 1.287 max, 0.045 min
msecs/first-response: 572.619 mean, 787.905 max, 373.871 min
126 bad byte counts
HTTP response codes:
  code 200 -- 135""".splitlines(), 3)
  assert 1399 == int(ret), ret


def parse_status_lines(lines):
  num_ok = 0
  num_err = 0
  for line in lines:
    ll, rr = line.split(' -- ')
    c = int(ll.split(' ')[-1])
    n = int(rr)
    if 200 == c:
      num_ok += n
    else:
      num_err += n
  return num_ok, num_err


def send_score(score):
  return #for admin's benchmark
  r = http_post(SCORE_HOST, '/post_result', {'score': score}, timeout=3)
  if r:
    print 'Score sending was succeeded.'
  else:
    print 'Score sending was failed.'


def main():
  from optparse import OptionParser
  
  parser = OptionParser()
  parser.add_option('-c', type='int', dest='concurrency', default=DEFAULT_CONCURRENCY,
    help='Number of multiple requests to make')
  parser.add_option('-s', type='int', dest='seconds', default=DEFAULT_SECONDS,
    help='Number of seconds to perform')
  parser.add_option("--mode", dest="mode", default=None)
  options, args = parser.parse_args()
  
  #run tests
  if 'test' == options.mode:
    test_parse_http_load_result()
    return
  
  if 1 != len(args):
    parser.print_help()
    return
  
  assert 1 <= options.concurrency <= 100
  assert 1 <= options.seconds <= 100
  
  #run bench
  old_sys_stderr = sys.stderr
  sys.stderr = StringIO()
  try:
    run_bench(args[0], options.seconds, options.concurrency)
  except Exception, e:
    print e
    import traceback
    print traceback.format_exc()
  except KeyboardInterrupt:
    print 'KeyboardInterrupt'
  finally:
    sys.stderr = old_sys_stderr


if __name__ == '__main__':
  main()
