# -*- coding: utf-8 -*-

import os
import time
import datetime
import sqlite3
import posixpath
import mimetypes
from zlib import adler32
from optparse import OptionParser
from werkzeug.local import LocalProxy
from werkzeug.wsgi import wrap_file
from raginei import Application, render, render_text, route, request, local, \
  response_middleware, template_filter, current_app, abort_if

application = Application.instance()


@route('/')
def index():
  c = db.cursor()
  sql = u"""SELECT * FROM result ORDER BY score DESC, updated DESC;"""
  results = c.execute(sql)
  return render('index', results=results)


@route('/history/<remote_addr>')
def show_history(remote_addr):
  c = db.cursor()
  sql = u"""SELECT * FROM history ORDER BY updated DESC LIMIT 100;"""
  results = c.execute(sql)
  return render('history', results=results)


@route('/post_result')
def post_result():
  insert_result()
  return render_text('OK')


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
  if mtime is not None:
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
    local.db = sqlite3.connect("data.db")
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
  import random
  c = db.cursor()
  c.execute(u"""DELETE FROM history;""")
  c.execute(u"""DELETE FROM result;""")
  now = time.time()
  for i in xrange(60):
    insert_result_impl( ('10.0.0.%d' % i, random.randint(1, 1000), now) )
  db.commit()


@template_filter
def time_to_date(unix_time):
  dt = datetime.datetime.fromtimestamp(unix_time)
  return dt.strftime('%H:%M:%S')


@template_filter
def format_score(score):
  return '%.3f' % score


def main():
  parser = OptionParser()
  parser.add_option("-r", "--run", action="store_true", dest="is_run",
    default=False, help="Run server")
  parser.add_option("-i", "--init", action="store_true", dest="is_init",
    default=False, help="Init database")
  parser.add_option("-t", "--t", action="store_true", dest="is_test",
    default=False, help="Load testdata")
  options, args = parser.parse_args()
  if options.is_run:
    return run_server()
  elif options.is_init:
    return init_database()
  elif options.is_test:
    return load_test_data()


if __name__ == '__main__':
  main()
