# -*- coding: utf-8 -*-

import os
import time
import datetime
import sqlite3
import posixpath
import mimetypes
import random
import functools
from zlib import adler32
from optparse import OptionParser
from werkzeug.local import LocalProxy
from werkzeug.wsgi import wrap_file
from raginei import Application, render, render_text, route, request, local, \
  response_middleware, template_filter, current_app, abort_if, fetch
from raginei.cache import cache_key

import config
application = Application.instance(**config.config)

import memcache
cache = memcache.Client(['127.0.0.1:11211'])


def memoize(expiry=300):
  rng = int(expiry / 5)
  def _decorator(func):
    @functools.wraps(func)
    def _wrapper(*args, **kwds):
      key = cache_key(func, *args, **kwds)
      now = time.time()
      data = None
      if expiry and cache and config.memoize:
        data_tuple = cache.get(key)
        if data_tuple:
          rnd = random.randint(-rng, rng)
          if data_tuple[1] >= int(now + rnd):
            data = data_tuple[0]
      if data is None:
        data = func(*args, **kwds)
        if expiry and cache:
          exp_time = int(now + expiry)
          cache.set(key, (data, exp_time), expiry + rng)
      return data
    return _wrapper
  return _decorator


@route('/')
def index():
  template = 'results' if request.is_xhr else 'index'
  return index_impl(template)


@memoize(30)
def index_impl(template):
  c = db.cursor()
  sql = u"""SELECT * FROM result ORDER BY score DESC, updated DESC;"""
  results = c.execute(sql)
  return fetch(template, results=results)


@route('/history/<remote_addr>')
def show_history(remote_addr):
  c = db.cursor()
  sql = u"""SELECT * FROM history WHERE name = ? ORDER BY updated DESC LIMIT 20;"""
  results = c.execute(sql, [remote_addr])
  return render('history', results=results, remote_addr=remote_addr)


@route('/post_result')
def post_result():
  ra = request.remote_addr
  if ra.startswith('10.') or ra.startswith('127.'):
    insert_result()
    return render_text('OK')
  return render_text('NG')


@route('/static/<path:filename>')
def static_file(filename):
  return send_file(filename)


def send_file(filename):
  filename = posixpath.normpath(filename)
  abort_if(filename.startswith(('/', '../')))
  filename = os.path.join(current_app.project_root, 'static', filename)
  abort_if(not os.path.isfile(filename))
  file = open(filename, 'rb')
  data = wrap_file(request.environ, file)
  mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
  rv = current_app.response_class(data, mimetype=mimetype, direct_passthrough=True)
  mtime = os.path.getmtime(filename)
  if mtime:
    rv.date = int(mtime)
  rv.cache_control.public = True
  cache_timeout = 3600
  rv.cache_control.max_age = cache_timeout
  rv.expires = int(time.time() + cache_timeout)
  rv.set_etag('%s-%s-%s' % (
    mtime,
    os.path.getsize(filename),
    adler32(filename) & 0xffffffff
  ))
  rv = rv.make_conditional(request)
  return rv


def insert_result():
  now = long(time.time())
  values = (request.remote_addr, float(request.args.get('score') or 0), now)
  insert_result_impl(values)
  if 0 == random.randint(0, 100):
    c = db.cursor()
    c.execute("""VACUUM;""")
    db.commit()


def insert_result_impl(values):
  c = db.cursor()
  sql = u"""INSERT INTO history (name,score,updated) VALUES (?,?,?);"""
  c.execute(sql, values)
  sql = u"""INSERT OR REPLACE INTO result (name,score,updated) VALUES (?,?,?);"""
  c.execute(sql, values)
  db.commit()


def init_database():
  c = db.cursor()
  c.execute(u"""
CREATE TABLE IF NOT EXISTS history (
  name TEXT NOT NULL,
  score REAL NOT NULL,
  updated INTEGER NOT NULL
);
""")
  c.execute(u"""
CREATE TABLE IF NOT EXISTS result (
  name TEXT NOT NULL UNIQUE,
  score REAL NOT NULL,
  updated INTEGER NOT NULL
);
""")
  db.commit()


def open_db():
  try:
    if not local.db:
      raise AttributeError()
  except (KeyError, AttributeError):
    local.db = sqlite3.connect(os.path.join(
      os.path.dirname(os.path.abspath(__file__)), 'data.db'))
  return local.db


db = LocalProxy(open_db)


@response_middleware
def close_db(response=None):
  try:
    if local.db:
      local.db.close()
      local.db = None
  except (KeyError, AttributeError):
    pass


def run_server():
  application.run(port=5050)


def load_test_data():
  c = db.cursor()
  c.execute(u"""DELETE FROM history;""")
  c.execute(u"""DELETE FROM result;""")
  now = time.time()
  for j in xrange(100):
    for i in xrange(60):
      values = ('10.0.0.%d' % i, random.randint(1, 1000), now - j * 10)
      print values
      insert_result_impl( values )
  db.commit()
  c = db.cursor()
  c.execute("""VACUUM;""")
  db.commit()


@template_filter
def time_to_date(unix_time):
  dt = datetime.datetime.fromtimestamp(unix_time)
  return dt.strftime('%H:%M:%S')


@template_filter
def format_score(score):
  return '%.3f' % score


@template_filter
def remote_addr_name(remote_addr):
  return config.remote_addr_names.get(remote_addr) or remote_addr


def main():
  parser = OptionParser()
  #parser.add_option("-r", "--run", action="store_true", dest="is_run",
  #  default=False, help="Run server")
  parser.add_option("-i", "--init", action="store_true", dest="is_init",
    default=False, help="Init database")
  parser.add_option("-t", "--t", action="store_true", dest="is_test",
    default=False, help="Load testdata")
  options, args = parser.parse_args()
  if options.is_init:
    return init_database()
  elif options.is_test:
    return load_test_data()
  return run_server()


if __name__ == '__main__':
  main()
