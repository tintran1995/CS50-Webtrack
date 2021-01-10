import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    # Display current portfolio
    usercash = db.execute("SELECT * FROM users WHERE id = :user_id", user_id = session["user_id"])
    cash = round(usercash[0]["cash"], 2)
    grandtotal = cash

    stocks = db.execute("SELECT * FROM (SELECT *, SUM(shares) as sumshare FROM stocks WHERE userid = :user_id GROUP BY symbol) WHERE sumshare > 0;", user_id = session["user_id"])

    for stock in stocks:
        stocklookup = lookup(stock["symbol"])
        stock["name"] = stocklookup["name"]
        stock["price"] = stocklookup["price"]
        stock["total"] = stock["sumshare"] * stock["price"]
        grandtotal = round(grandtotal + stock["total"], 2)

    return render_template("index.html", rows = stocks, cash = cash, grandtotal = grandtotal)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    # Render buy.html if method is GET
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        shares = float(request.form.get("shares"))
        stock = lookup(symbol)

        # Render apology if symbol is blank or invalid
        if not symbol or not stock:
            return apology("Symbol is blank or stock with the entered symbol does not exist", 403)
        elif shares <= 0:
            return apology("Must enter positive integer for amount of shares to buy", 403)
        else:
            # Assign current stock name, symbol and price
            stockname = stock["name"]
            symbol = stock["symbol"]
            price = float(stock["price"])

            # Find out how much cash user has
            row = db.execute("SELECT * FROM users WHERE id = :user_id", user_id = session["user_id"])
            cash = row[0]["cash"]
            if (shares * price) > cash:
                return apology("not enough cash to buy", 403)
            else:
                db.execute("INSERT INTO stocks (userid, symbol, shares, price, date) VALUES (:user_id, :symbol, :shares, :price, :date)", user_id = session["user_id"], symbol = symbol, shares = shares, price = price, date = datetime.now())
                db.execute("UPDATE users SET cash = :remainingcash WHERE id = :user_id", remainingcash = cash - shares * price, user_id = session["user_id"])
                return redirect("/")


@app.route("/history")
@login_required
def history():
    # Show history of purchases
    stocks = db.execute("SELECT * FROM stocks WHERE userid = :user_id ORDER BY date ASC", user_id = session["user_id"])

    return render_template("history.html", rows = stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():

    # Render quote if user visits via GET
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        # Render apology if symbol is invalid
        if not stock:
            return apology(f"stock with symbol {symbol} does not exist", 403)
        else:
            return render_template("quoted.html", stockname = stock["name"], symbol = stock["symbol"], price = stock["price"])


@app.route("/register", methods=["GET", "POST"])
def register():

    # Return register page if method is GET
    if request.method == "GET":
        return render_template("register.html")

    else:
        # If method is POST, register user after checking credentials are valid
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username = username)

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 403)

        # Check if username already exits
        elif len(rows) != 0:
            return apology("username already exists", 403)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 403)

        # Ensure password confirmation was submitted
        elif not confirmation:
            return apology("must re-type password", 403)

        # ensure password and confirmation match
        elif password != confirmation:
            return apology("password and confirmation do not match", 403)

        else:
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :passwordhash)", username = username, passwordhash = generate_password_hash(password))
            return render_template("login.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    # Return sell.html if method is GET
    if request.method == "GET":
        rows = db.execute("SELECT * FROM (SELECT *, SUM(shares) as sumshare FROM stocks WHERE userid = :user_id GROUP BY symbol) WHERE sumshare > 0;", user_id = session["user_id"])
        return render_template("sell.html", rows = rows)
    else:
        # Sell stock if method is PUSH
        symbol = request.form.get("symbol")
        shares = float(request.form.get("shares"))
        stock = lookup(symbol)
        sumshares = db.execute("SELECT SUM(shares) as sumshare FROM stocks WHERE userid = :user_id AND symbol = :symbol", user_id = session["user_id"], symbol = symbol)

        # Render apology if symbol is blank or user has no stock
        if not symbol:
            return apology("Must select a stock symbol", 403)
        elif sumshares[0]["sumshare"] <= 0:
            return apology("Have no share in this stock")
        elif shares <= 0:
            return apology("Must enter positive integer for amount of shares to sell", 403)
        elif shares > sumshares[0]["sumshare"]:
            return apology("Does not own that many shares to sell", 403)
        else:
            # Assign current stock name, symbol and price
            stockname = stock["name"]
            symbol = stock["symbol"]
            price = float(stock["price"])

            # Find out how much cash user has
            row = db.execute("SELECT * FROM users WHERE id = :user_id", user_id = session["user_id"])
            cash = row[0]["cash"]
            db.execute("INSERT INTO stocks (userid, symbol, shares, price, date) VALUES (:user_id, :symbol, :shares, :price, :date)", user_id = session["user_id"], symbol = symbol, shares = -shares, price = price, date = datetime.now())
            db.execute("UPDATE users SET cash = :remainingcash WHERE id = :user_id", remainingcash = cash + shares * price, user_id = session["user_id"])
            return redirect("/")

@app.route("/watch", methods=["GET", "POST"])
@login_required
def watch():
    # Show watchlist

    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)

        # Render apology if symbol is blank or invalid
        if not symbol or not stock:
            return apology("Symbol is blank or stock with the entered symbol does not exist", 403)
        else:
            # Assign current stock name, symbol and price
            symbol = stock["symbol"]
            price = float(stock["price"])
            watchlist = db.execute("SELECT * FROM watch WHERE userid = :user_id AND symbol = :symbol ORDER BY symbol ASC", user_id = session["user_id"], symbol = symbol)

            if not watchlist:
                db.execute("INSERT INTO watch (userid, symbol, price) values (:user_id, :symbol, :price)", user_id = session["user_id"], symbol = symbol, price = price)

    watchlist = db.execute("SELECT * FROM watch WHERE userid = :user_id ORDER BY symbol ASC", user_id = session["user_id"])
    for row in watchlist:
        stock = lookup(row["symbol"])
        price = float(stock["price"])
        db.execute("UPDATE watch SET price = :price WHERE userid = :user_id AND symbol = :symbol", price = price, user_id = row["userid"], symbol = row["symbol"])
    watchlist = db.execute("SELECT * FROM watch WHERE userid = :user_id ORDER BY symbol ASC", user_id = session["user_id"])
    return render_template("watch.html", rows = watchlist)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
