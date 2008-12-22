#!/usr/bin/env python
# author: Jesse Shieh (jesse.shieh@gmail.com)

import os
import random
import re
import time
import wsgiref.handlers
from google.appengine.api import mail
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class Game(db.Model):
  creator = db.StringProperty(required=True)
  invitees = db.StringListProperty()

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

  # translate the array cycle into a dictionary (could be useful)
  # TODO(jesses): consider putting this in a more appropriate class
  def create_assignment_dictionary(self, list):
    assignments = {}
    for i in range(len(list) - 1):
      assignments[list[i]] = list[i + 1]
    assignments[list[-1]] = list[0]
    return assignments

class MainHandler(BaseHandler):
  def get(self):
    self.render("main.html")

class ManageHandler(BaseHandler):
  def get(self):
    self.render("manage.html")

class EmailHandler(BaseHandler):
  def get(self):
    code = self.request.get("code")
    game = db.get(db.Key(code))

    assignments = self.create_assignment_dictionary(game.invitees)
    for key in assignments.keys():
      value = assignments[key]
      # send mail invitee
      self.add_template_value("giver", key)
      self.add_template_value("receiver", value)
      html_body = template.render(os.path.join(os.path.dirname(__file__),
                                               "invitee_email.html"),
                                  self.template_values)
      mail.send_mail(sender="jesse.shieh@gmail.com",
                     to=key,
                     cc="jesse.shieh+secretsanta@gmail.com",
                     subject="Your Secret Santa Assignment",
                     body=html_body,
                     html=html_body)

      # app engine has an annoying throttling issue that limits the speed
      # at which emails can be sent.  sleep to kind of help it.  this
      # obviously isn't sufficient for any kind of real production system
      time.sleep(24 * 60 * 60 / 2000)

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

class ConfirmHandler(BaseHandler):
  # randomize an array
  def randomize(self, list):
    length = len(list)
    for i in range(length):
      j = random.randrange(i, length)
      list[i], list[j] = list[j], list[i]

  def post(self):
    creator = self.request.get("creator")

    # list of invitees (don't forget to add the creator)
    invitees = [creator]

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

    # randomize the order of invitees
    self.randomize(invitees)

    # insert game into datastore
    game = Game(creator=creator,
                invitees=invitees)
    game.put()

    assignments = self.create_assignment_dictionary(invitees)

    # populate template values
    self.add_template_value("creator", creator)
    self.add_template_value_from_request("price")
    self.add_template_value("assignments", assignments)
    self.add_template_value("code", game.key())

    # send mail to creator using same template_values
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                             "confirm_email.html"),
                                self.template_values)
    mail.send_mail(sender="jesse.shieh@gmail.com",
                   to=creator,
                   cc="jesse.shieh+secretsanta@gmail.com",
                   subject="Your Secret Santa Gift Exchange",
                   body=html_body,
                   html=html_body)

    # render
    self.render("confirm.html")

def main():
  # boilerplate application registration stuff
  application = webapp.WSGIApplication([("/", MainHandler),
                                        ("/email", EmailHandler),
                                        ("/confirm", ConfirmHandler),
                                        ("/manage", ManageHandler)],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()
