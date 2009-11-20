#!/usr/bin/env python
# author: Jesse Shieh (jesse.shieh@gmail.com)

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

class NotFoundPageHandler(webapp.RequestHandler):
  def get(self):
    self.error(404)
    self.response.out.write('Not Found')

def main():
  application = webapp.WSGIApplication([('/.*', NotFoundPageHandler)],
                                         debug=True)
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
