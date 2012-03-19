# -*- coding: utf-8 -*-

import sys
import logging
import threading
import httplib
try:
  from cStringIO import StringIO
except ImportError:
  from StringIO import StringIO

SCORE_HOST = '175.41.237.139'
URL_TXT = '/home/bench/url.txt'
HTTP_LOAD = '/home/bench/http_load'


def print_console(s):
  sys.stdout.write(s)
  sys.stdout.flush()


class CheckerThread(object):
  
  def __init__(self, host, path, num):
    self._host = host
    self._path = path
    self._num = num
    self._lock = threading.Lock()
    self._cond = threading.Condition(threading.Lock())
    self._thread = threading.Thread(target=self._run)
    self._thread.daemon = True
    self._value = None
    self._ready = False
    self._success = False
  
  def _run(self):
    try:
      for i in xrange(self.num):
        
        #TODO: GETs and POSTs
        http_get(self._host, self._path)
        
        self.print_dot()
      
      self._value = True
      self._success = True
      
    except Exception, e:
      self._value = e
      self._success = False
      
    finally:
      self._cond.acquire()
      try:
        self._ready = True
        self._cond.notify()
      finally:
        self._cond.release()
  
  def print_dot(self):
    self._lock.acquire()
    try:
      self._loop += 1
      if 1 == self._loop % 10:
        print_console('.')
    finally:
      self._lock.release()
  
  def start(self):
    self._thread.start()
  
  def wait(self, timeout=None):
    self._cond.acquire()
    try:
      if not self._ready:
        self._cond.wait(timeout or 60)
    finally:
      self._cond.release()
  
  def get(self, timeout=None):
    self.wait(timeout)
    if self._success:
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
  headers = {'User-Agent': 'http_load 12mar2006', 'Connection': 'close'}
  conn = httplib.HTTPConnection(host, timeout=timeout)
  try:
    conn.request("POST", path, params, headers=headers)
    r = conn.getresponse()
    status = r.status
    if 200 != status:
      return status
    return r.read() #OK
  finally:
    conn.close()
 

def run_bench(host, requests, concurrency):
  from subprocess import Popen, PIPE, STDOUT
  
  concurrency = min(concurrency, requests)
  
  #http://localhost/foo/bar
  host, path = host.split('//', 1)[1].split('/', 1)
  path = '/' + path
  
  #create URL_TXT for http_load
  f = open(URL_TXT, 'wb')
  try:
    f.write('http://%s%s', (host, path))
  finally:
    f.close()
  
  http_load_requests = int(requests * (concurrency - 1) / concurrency)
  checker_requests = requests - http_load_requests
  
  #start CheckerThread
  checker = CheckerThread(host, path, checker_requests)
  checker.start()
  
  #http_load -parallel 10 -fetches 100 url.txt
  args = [HTTP_LOAD, '-parallel', str(concurrency - 1),
    '-fetches', str(http_load_requests), URL_TXT]
  p = Popen(args, stdout=PIPE, stderr=STDOUT)
  
  #wait http_load
  try:
    rets = []
    for line in p.stdout.readlines():
      line = line.rstrip()
      rets.append(line)
      print line
    p.wait()
  except:
    p.terminate()
    raise
  
  """
49 fetches, 2 max parallel, 289884 bytes, in 10.0148 seconds
5916 mean bytes/connection
4.89274 fetches/sec, 28945.5 bytes/sec
msecs/connect: 28.8932 mean, 44.243 max, 24.488 min
msecs/first-response: 63.5362 mean, 81.624 max, 57.803 min
HTTP response codes:
  code 200 -- 49
  """
  
  #parse result of http_load
  assert rets[0].split(',')[0].startswith(str(requests))
  assert rets[5] == 'HTTP response codes:'
  
  num_ok = 0
  num_err = 0
  for ret in rets[6:]:
    ll, rr = ret.split(' -- ')
    c = int(ll.split(' ')[-1])
    n = int(rr)
    if 200 == c:
      num_ok += n
    else:
      num_err += n
  assert num_ok + num_err == requests
  
  elapsed = float(rets[0].split(' in ')[-1].split(' ')[0])
  succeeds_percent = num_ok / requests
  assert 1.0 >= succeeds_percent
  
  #calculate score
  score = requests / (elapsed or 0.0000001)
  score = score * succeeds_percent * succeeds_percent
  
  #get result of CheckerThread
  checker_result = checker.get()
  check_percent = checker_result / requests
  assert 1.0 >= check_percent
  score = score * check_percent * check_percent
  
  print 'Score: %.3f' % score
  
  #post score to score server
  if 100 <= requests and 10 == concurrency:
    send_score(score)
  
  return score


def send_score(score):
  r = http_post(SCORE_HOST, '/post_result', {'score': score}, timeout=3)
  if r:
    print 'Score sending was succeeded.'
  else:
    print 'Score sending was failed.'


def main():
  from optparse import OptionParser
  
  parser = OptionParser()
  parser.add_option('-c', type='int', dest='concurrency', default=10,
    help='Number of multiple requests to make')
  parser.add_option('-n', type='int', dest='requests', default=100,
    help='Number of requests to perform')
  
  options, args = parser.parse_args()
  if 1 != len(args):
    parser.print_help()
    return
  
  assert 1 <= options.concurrency <= 100
  assert 1 <= options.requests <= 10000
  
  host = args[0]
  if not host.startswith('http://'):
    print 'URL is invalid.'
    return
  
  old_sys_stderr = sys.stderr
  sys.stderr = StringIO()
  try:
    run_bench(host, options.requests, options.concurrency)
  except Exception, e:
    print e
    logging.exception(e)
  except KeyboardInterrupt:
    print 'KeyboardInterrupt'
  finally:
    sys.stderr = old_sys_stderr


if __name__ == '__main__':
  main()
