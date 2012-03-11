# -*- coding: utf-8 -*-

debug = True
memoize = False

if debug: #develop
  config = dict(jinja2_loader='jinja2.FileSystemLoader')
else: #production
  config = dict(jinja2_loader='raginei.jinja2loader.FileSystemLoader')

remote_addr_names = {
  '10.0.0.0': 'test',
}
