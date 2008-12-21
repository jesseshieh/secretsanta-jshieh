#!/usr/bin/env python
# author: Jesse Shieh (jesse.shieh@gmail.com)

import os
import re
import wsgiref.handlers
from google.appengine.api import mail
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class BaseHandler(webapp.RequestHandler):
  template_values = {
    "title": "Secret Santa",
    }

  # adds a new entry in the template dictionary
  def add_template_value(self, key, value):
    self.template_values[key] = value

  # special case of add_template_value that pulls the value from the
  # request object (it's a url parameter of the same name)
  def add_template_value_from_request(self, key):
    self.add_template_value(key, self.request.get(key))

  # renders and writes the response given the template name
  def render(self, template_name):
    path = os.path.join(os.path.dirname(__file__), template_name)
    self.response.out.write(template.render(path, self.template_values))

class MainHandler(BaseHandler):
  def get(self):
    self.render("main.html")

class ConfirmHandler(BaseHandler):
  def post(self):
    creator = self.request.get("creator")

    # list of invitees (not including creator)
    invitees = []

    # invitee post parameter regular expression
    invitee_re = re.compile(r"invitee(\d+)")

    # iterate through args
    for key in self.request.arguments():
      # if this is an invitee, then add it to the invitee array
      if invitee_re.match(key):
        value = self.request.get(key)

        # don't include empty params
        if len(value) != 0:
          invitees.append(value)

    # this secret santa instance's manager code
    code = "abc123"

    # populate template values
    self.add_template_value("creator", creator)
    self.add_template_value_from_request("price")
    self.add_template_value("invitees", invitees)
    self.add_template_value("code", code)

    # send mail to creator using same template_values
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                        "confirm_email.html"),
                           self.template_values)
    mail.send_mail(sender="jesse.shieh@gmail.com",
                   to=creator,
                   subject="Your secret santa manager code",
                   html=html_body)

    # render
    self.render("confirm.html")


def main():
  # boilerplate application registration stuff
  application = webapp.WSGIApplication([("/", MainHandler),
                                        ("/confirm", ConfirmHandler)],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()
