import cgi
import datetime
import urllib
import wsgiref.handlers

from datetime import timedelta
from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

msk_delta = timedelta(hours=4)

class LogEntry(db.Model):
  client = db.StringProperty()
  spot = db.StringProperty()
  action = db.StringProperty()
  auth = db.StringProperty()
  nobadge = db.BooleanProperty()
  date = db.DateTimeProperty(auto_now_add=True)

class Client(db.Model):
  client = db.StringProperty()
  hid = db.StringProperty()

class Spot(db.Model):
  spot = db.StringProperty()
  occupied = db.BooleanProperty()
  booked = db.BooleanProperty()
  client = db.StringProperty()
  date = db.DateTimeProperty()

def log_key():
  return db.Key.from_path("LogEntry", "default_table")

def client_key():
  return db.Key.from_path("Client", "default_table")

def spot_key():
  return db.Key.from_path("Spot", "default_table")

class BaseHandler(webapp.RequestHandler):
  def clear_spot(self, spot):
    spot.occupied = False
    spot.booked = False
    spot.client = "free"
    spot.date = datetime.datetime.now()
    spot.put()

  def spots(self):
    spots = db.GqlQuery("SELECT * FROM Spot WHERE ANCESTOR IS :1 ORDER BY spot", spot_key())
    result = []
    for spot in spots:
      if spot.occupied and datetime.datetime.now() - spot.date > timedelta(hours=12):
        self.clear_spot(spot)
      elif spot.booked and datetime.datetime.now() - spot.date > timedelta(minutes=20):
        self.clear_spot(spot)
      result.append(spot)
    return result

  def load_clients(self):
    clients = db.GqlQuery("SELECT * FROM Client WHERE ANCESTOR IS :1 ORDER BY client", client_key())
    self.clients = {}
    for client in clients:
      self.clients[client.hid] = client.client

  def is_checked_in(self, client_id):
    for spot in self.spots():
      if spot.occupied == True and spot.client == client_id:
        return True
    return False

  def clear_dupes(self, spot_id, client_id):
    for spot in self.spots():
      if spot.spot != spot_id and spot.client == client_id:
        spot.occupied = False
        spot.booked = False
        spot.client = "free"
        spot.date = datetime.datetime.now()
        spot.put()

  def get_client_id(self):
    self.load_clients()
    client_hid = self.request.get("hid")
    if client_hid in self.clients:
      self.nobadge = False
      return self.clients[client_hid]
    self.nobadge = True
    return self.request.get("client")

  def get_auth_client_id(self):
    user = users.get_current_user()
    if user:
      domain = user.nickname().find("@google.com")
      if domain == -1:
        return None
      return user.nickname()[0:domain]
    return None

  def authenticate(self, redirect):
    client_id = self.get_auth_client_id()
    if not client_id:
      greeting = "<a href=\"%s\">Sign in with your corp account!</a>." % users.create_login_url(redirect)
      self.response.out.write("<html><body>%s</body></html>" % greeting)
      return False
    return True

  def is_valid_client_id(self, client_id):
    for hid in self.clients:
      if self.clients[hid] == client_id:
        return True
    return False

  def ordered_client_ids(self):
    ordered_clients = []
    for hid in self.clients:
      ordered_clients.append(self.clients[hid])
    ordered_clients.sort()
    return ordered_clients

  def emit_client_list(self, base):
    self.response.out.write("""
        <html>
        <style>
        table { height: 100%; width: 100% }
        td { text-align: center; border: 10px solid white; font-size: 40px; width: 50%; cursor: pointer; background-color: lightgreen }
        .gap { background-color: white; }
        </style>
        <body style='font-size:50px'>
        <div style="text-align:center">choose your name:</div>""")
    if not base:
      base = ""
    client_list = self.ordered_client_ids()
    self.response.out.write("<table>")
    for i in range((len(client_list) + 1) / 2):
      client = client_list[2 * i];
      self.response.out.write("<tr>")
      self.response.out.write("<td><a href='/%s?client=%s'>%s</a></td>" % (base, client, client))
      if 2 * i + 1 < len(client_list):
        client = client_list[2 * i + 1];
        self.response.out.write("<td><a href='/%s?client=%s'>%s</a></td>" % (base, client, client))  
      self.response.out.write("</tr>")
    self.response.out.write("<tr><td class='gap'>&nbsp;</td><td class='gap'>&nbsp;</td></tr>")
    self.response.out.write("</table>")
    self.response.out.write("</body></html>")

  def emit_cell(self, spot):
    self.response.out.write("""
        <td onclick='onClick(\"%s\")' class='spot occupied-%s booked-%s'>
          <div>%s : %s</div>
          <div class='date'>%s</div>
        </td>""" % (spot.spot, spot.occupied, spot.booked, spot.spot, spot.client, (spot.date + msk_delta).strftime("%H:%M (%d/%m/%y)")))

  def emit_chips(self, action, cell_message, info_message):
    self.response.out.write("""
      <html>
      <style>
      form { display: none }
      table { height: 100%; width: 100% }
      td { text-align: center; border: 10px solid white; font-size: 40px; width: 50%; cursor: pointer }
      .smaller { font-size: 35px; }
      .occupied-True { background-color: lightpink !important }
      .occupied-False { background-color: lightgreen }
      .booked-True { background-color: lightyellow }
      .booked-False { background-color: lightgreen }
      .date { display: none }
      .booked-True .date, .occupied-True .date { display: block; font-size: 30px; }
      .refresh { float: right }
      </style>
      <script>
      function onload()
      {
        if (navigator.userAgent.match(/Android/i))
          window.scrollTo(0,1);
        setTimeout(function() { window.location.reload(); }, 30000);
      }
      function onClick(spot)
      {
      }
      </script>
      <body onload='onload()'>""")

    if action:
      self.response.out.write("""
          <script>
          function onClick(spot)
          {
            document.getElementById("spot").value = spot;
            document.forms.myform.submit()
          }
          </script>
          <form id="myform" action="/%s" method="post">
            <div><input name="client" hidden=true value="%s"></input></div>
            <div><input name="hid" hidden=true value="%s"></input></div>
            <div><input id="spot" name="spot" hidden=true></input></div>
          </form>""" % (action, self.request.get("client"), self.request.get("hid")))

    spot_list = self.spots()
    self.response.out.write("<table>")
    for i in range((len(spot_list) + 1) / 2):
      self.response.out.write("<tr>")
      self.emit_cell(spot_list[2 * i])
      if 2 * i + 1 < len(spot_list):
        self.emit_cell(spot_list[2 * i + 1])
      elif cell_message:
        self.response.out.write("<td>" + cell_message + "</td>")
      self.response.out.write("</tr>")
    if info_message:
      self.response.out.write("<tr>")
      self.response.out.write("<td colspan=2>" + info_message + "</td>")
      self.response.out.write("<tr>")

    self.response.out.write("</table>")
    self.response.out.write("</body></html>")

  def emit_confirm_checkout(self, client_id):
    self.response.out.write("""
      <html>
      <style>
      body { font-size: 25px }
      button { margin: 10px; padding: 10px; font-size: 25px }
      form { display: none }
      </style>
      <body>
      <h1>Confirm check out, %s</h1>
      <script>setTimeout(function() { document.forms.myform.submit() }, 15000)</script>
      <button onclick="document.forms.myform.submit()">Yes, I do checkout</button><br>
      <button onclick="window.location='/'">No, thanks</button><br>
      not %s? <a href="/list?redirect=nobadge">click here</a><br>
      <form id="myform" action="/checkout" method="post">
        <div><input name="hid" hidden=true value="%s"></input></div>
        <div><input name="client" hidden=true value="%s"></input></div>
      </form>
      </body>
      </html>""" % (client_id, client_id, self.request.get("hid"), client_id))

class Log(BaseHandler):
  def get(self):
    self.response.out.write("<html><body><h3>Log</h3>")
    entries = db.GqlQuery("SELECT * "
                          "FROM LogEntry "
                          "WHERE ANCESTOR IS :1 "
                          "ORDER BY date DESC LIMIT 100",
                          log_key())
    self.response.out.write("<table width='100%' border=1>")
    self.response.out.write("<th>Name</th><th>Spot</th><th>Action</th><th>Date</th><th>No badge</th><th>Auth</th></div>")
    for entry in entries:
      if entry.nobadge and entry.action == "checkin":
        self.response.out.write("<tr style='color:red'>")
      else:
        self.response.out.write("<tr>")
      self.response.out.write("<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></div>" % (entry.client, entry.spot, entry.action, (entry.date + msk_delta).strftime("%H:%M (%d/%m/%y)"), entry.nobadge, entry.auth))
      self.response.out.write("</tr>")  
    self.response.out.write("</table>")

    self.response.out.write("</body></html>")

class Landing(BaseHandler):
  def post(self):
    self.get()

  def get(self):
    user_agent = ""
    if "User-Agent" in self.request.headers:
      user_agent = self.request.headers["User-Agent"]
    if user_agent.find("Mobile") != -1 or self.request.get('mobile'):
      self.redirect("/m")
      return

    cell_message = """
        <script>
        function badgeSwiped(hid)
        {
            document.getElementById("hid").value = hid;
            document.forms.myform.submit()
        }
        </script>
        <div>Swipe your badge</div>
        <form id="myform" action="/" method="post">
        <div><input id="hid" name="hid" hidden=true value="%s"></input></div>
        </form>"""
    info_message = "<div>no badge? <a href='/nobadge'>click here</a></div>"
    self.emit_chips(None, cell_message, info_message)

class NoBadge(BaseHandler):
  def post(self):
    self.get()

  def get(self):
    if not self.authenticate("/nobadge"):
      return

    client_id = self.get_client_id()
    if not client_id:
      client_id = self.get_auth_client_id()

    if self.is_valid_client_id(client_id):
      if self.is_checked_in(client_id):
        self.emit_confirm_checkout(client_id)
      else:
        cell_message = """
            <script>setTimeout(function() { window.location = "/"; }, 15000)</script>
            <div style="color:red">Check in, %s!</div>
            <div>not %s? <a href='/list?redirect=nobadge'>click here</a></div>
            <div><a href="/">cancel</a></div>""" % (client_id, client_id)
        self.emit_chips("checkin", cell_message, None)
    else:
      self.emit_client_list("nobadge")

class Mobile(BaseHandler):
  def get(self):
    client_id = self.get_client_id()
    if client_id and self.is_valid_client_id(client_id):
      if not self.is_checked_in(client_id):
        cell_message = """<div>Book it, %s!</div>""" % client_id
        info_message = """<div class="smaller">not %s? <a href="/m">click here</a></div>""" % client_id
        self.emit_chips("book", cell_message, info_message)
      else:
        cell_message = """
            <div>You are checked in, %s!</div>
            <div class="smaller">&nbsp;</div>""" % client_id
        info_message = """
            <div class="smaller">not %s? <a href='/m'>click here</a> <a class="refresh" href='/m?client=%s'>refresh</a></div>""" % (client_id, client_id)
        self.emit_chips(None, cell_message, info_message)
    else:
      self.emit_client_list("m")

class List(BaseHandler):
  def get(self):
    self.load_clients()
    self.emit_client_list(self.request.get("redirect"))

class Book(BaseHandler):
  def post(self):
    spot_id = self.request.get("spot")
    client_id = self.get_client_id()
    if not self.is_valid_client_id(client_id):
      self.redirect("/m")
      return

    if self.is_checked_in(client_id):
      self.redirect("/m?client=%s" % client_id)
      return

    success = False
    for spot in self.spots():
      if spot.spot == spot_id and spot.client == client_id:
        entry = LogEntry(parent=log_key(), client=client_id, spot=spot_id, action="unbook", nobadge=self.nobadge)
        spot.booked = False
        spot.date = datetime.datetime.now()
        spot.client = "free"
        db.put([entry, spot])
        success = True
      elif spot.spot == spot_id and not spot.occupied and not spot.booked:
        entry = LogEntry(parent=log_key(), client=client_id, spot=spot_id, action="book", nobadge=self.nobadge)
        spot.booked = True
        spot.date = datetime.datetime.now()
        spot.client = client_id
        db.put([entry, spot])
        success = True
        break

    if success:
      self.clear_dupes(spot_id, client_id)

    self.redirect("/m?client=%s" % client_id)

class CheckIn(BaseHandler):
  def get(self):
    self.post()
  def post(self):
    if not self.authenticate("/checkin"):
      return
    client_id = self.get_client_id()
    auth_client_id = self.get_auth_client_id()
    if not client_id:
      client_id = auth_client_id

    if not client_id or self.is_checked_in(client_id):
      self.redirect("/")
      return

    spot_id = self.request.get("spot")

    success = False
    for spot in self.spots():
      if spot.spot == spot_id and (spot.client == client_id or not spot.occupied):
        entry = LogEntry(parent=log_key(), client=client_id, spot=spot_id, action="checkin", nobadge=self.nobadge, auth=auth_client_id)
        spot.occupied = True
        spot.booked = False
        spot.date = datetime.datetime.now()
        spot.client = entry.client
        db.put([entry, spot])
        success = True
        break

    if success:
      self.clear_dupes(spot_id, client_id)
    self.redirect("/")

class CheckOut(BaseHandler):
  def get(self):
    self.post()
  def post(self):
    if not self.authenticate("/checkout"):
      return

    client_id = self.get_client_id()
    auth_client_id = self.get_auth_client_id()
    if not client_id:
      client_id = auth_client_id

    if not client_id or not self.is_checked_in(client_id):
      self.redirect("/")
      return

    success = False
    for spot in self.spots():
      if spot.occupied and spot.client == client_id:
        entry = LogEntry(parent=log_key(), client=client_id, spot=spot.spot, action="checkout", nobadge=self.nobadge, auth=auth_client_id)
        spot.occupied = False
        spot.date = datetime.datetime.now()
        spot.client = "free"
        db.put([entry, spot])
        success = True

    if success:
      self.clear_dupes(None, client_id)
    self.redirect("/")

class Reset(BaseHandler):
  def get(self):
    if not self.authenticate("/resetresetreset"):
      return

    for spot in self.spots():
      spot.delete()

    spot_ids = ["01", "02", "09", "11", "13", "14", "15"]
    for spot_id in spot_ids:
      spot = Spot(parent=spot_key(), key_name=spot_id)
      spot.spot = spot_id
      spot.occupied = False
      spot.booked = False
      spot.date = datetime.datetime.now()
      spot.client = "free"
      spot.put()

    self.redirect('/')

application = webapp.WSGIApplication([
  ('/', Landing),
  ('/nobadge', NoBadge),
  ('/m', Mobile),
  ('/book', Book),
  ('/checkin', CheckIn),
  ('/checkout', CheckOut),
  ('/list', List),
  ('/resetresetreset', Reset),
  ('/log', Log)
], debug=True)


def main():
  run_wsgi_app(application)


if __name__ == '__main__':
  main()
