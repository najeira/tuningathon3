# -*- coding: utf-8 -*-

import os
import time
import datetime
import sqlite3
import random
import functools
from optparse import OptionParser
from werkzeug.local import LocalProxy
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
  insert_result()
  return render_text('OK')


def insert_result():
  now = long(time.time())
  values = (request.remote_addr, float(request.form.get('score') or 0), now)
  insert_result_impl(values)
  if 0 == random.randint(0, 100):
    vacuum_db()


def vacuum_db():
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


def init_db():
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


def insert_test_data():
  c = db.cursor()
  now = time.time()
  for i in xrange(60):
    values = ('175.41.237.%d' % i, random.randint(10, 200), now)
    insert_result_impl( values )
  db.commit()
  c = db.cursor()
  c.execute("""VACUUM;""")
  db.commit()


def delete_data():
  c = db.cursor()
  c.execute(u"""DELETE FROM history;""")
  c.execute(u"""DELETE FROM result;""")
  db.commit()
  vacuum_db()


@template_filter
def time_to_date(unix_time):
  dt = datetime.datetime.fromtimestamp(unix_time)
  from raginei.timezone import jst
  dt = jst(dt)
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
  
  parser.add_option("--init", action="store_true", dest="is_init",
    default=False, help="Init database")
  
  parser.add_option("--test", action="store_true", dest="is_test",
    default=False, help="Insert testdata")
  
  parser.add_option("--delete", action="store_true", dest="is_delete_data",
    default=False, help="Delete data")
  
  parser.add_option("--vacuum", action="store_true", dest="is_vacuum",
    default=False, help="Vacuum database")
  
  options, args = parser.parse_args()
  
  if options.is_init:
    return init_db()
    
  elif options.is_test:
    return insert_test_data()
    
  elif options.is_delete_data:
    return delete_data()
    
  elif options.is_vacuum:
    return vacuum_db()
  
  return run_server()


if __name__ == '__main__':
  main()
