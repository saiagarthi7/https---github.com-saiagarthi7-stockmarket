from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal, engine, User, Stock, Transaction, Base
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
import random
import time

app = FastAPI()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Background scheduler to update stock prices every 5 minutes
scheduler = BackgroundScheduler()

def update_stock_prices():
    db = SessionLocal()
    stocks = db.query(Stock).all()
    for stock in stocks:
        stock.price = round(random.uniform(1, 100), 2)  # Random price between 1-100
    db.commit()
    db.close()

scheduler.add_job(update_stock_prices, "interval", minutes=1)
scheduler.start()

# Pydantic model for stock registration
class StockCreate(BaseModel):
    name: str
    price: float
    available_quantity: int

class UserCreate(BaseModel):
    name: str

@app.post("/users/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.name == user.name).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(name=user.name, balance=100000, loan_taken=0)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User registered successfully", "user": new_user}


@app.post("/stocks/register")
def register_stock(stock: StockCreate, db: Session = Depends(get_db)):
    existing_stock = db.query(Stock).filter(Stock.name == stock.name).first()
    if existing_stock:
        raise HTTPException(status_code=400, detail="Stock already exists")

    new_stock = Stock(name=stock.name, price=stock.price, available_quantity=stock.available_quantity)
    db.add(new_stock)
    db.commit()
    db.refresh(new_stock)
    return {"message": "Stock registered successfully", "stock": new_stock}

@app.get("/stocks/history")
def get_stock_history(db: Session = Depends(get_db)):
    stocks = db.query(Stock).all()
    return {"stocks": stocks}
class LoanRequest(BaseModel):
    user_id: int
    amount: float

@app.post("/users/loan")
def take_loan(loan: LoanRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == loan.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.loan_taken + loan.amount > 100000:
        raise HTTPException(status_code=400, detail="Loan limit exceeded (Max: 100000)")

    user.balance += loan.amount
    user.loan_taken += loan.amount
    db.commit()
    return {"message": "Loan approved", "new_balance": user.balance}
class TradeRequest(BaseModel):
    user_id: int
    stock_id: int
    quantity: int

@app.post("/users/buy")
def buy_stock(trade: TradeRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == trade.user_id).first()
    stock = db.query(Stock).filter(Stock.id == trade.stock_id).first()

    if not user or not stock:
        raise HTTPException(status_code=404, detail="User or Stock not found")
    
    total_cost = trade.quantity * stock.price
    if user.balance < total_cost:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    if stock.available_quantity < trade.quantity:
        raise HTTPException(status_code=400, detail="Not enough stock available")

    # Deduct balance, reduce stock quantity, and record transaction
    user.balance -= total_cost
    stock.available_quantity -= trade.quantity
    new_transaction = Transaction(user_id=user.id, stock_id=stock.id, quantity=trade.quantity, price=stock.price, type="buy")

    db.add(new_transaction)
    db.commit()
    return {"message": "Stock purchased", "new_balance": user.balance}

@app.post("/users/sell")
def sell_stock(trade: TradeRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == trade.user_id).first()
    stock = db.query(Stock).filter(Stock.id == trade.stock_id).first()

    if not user or not stock:
        raise HTTPException(status_code=404, detail="User or Stock not found")

    total_sale = trade.quantity * stock.price
    user.balance += total_sale

    new_transaction = Transaction(user_id=user.id, stock_id=stock.id, quantity=trade.quantity, price=stock.price, type="sell")

    db.add(new_transaction)
    db.commit()
    return {"message": "Stock sold", "new_balance": user.balance}
@app.get("/users/report")
def user_report(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return {"users": users}

@app.get("/stocks/report")
def stock_report(db: Session = Depends(get_db)):
    stocks = db.query(Stock).all()
    return {"stocks": stocks}

@app.get("/users/top")
def top_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.balance.desc()).limit(5).all()
    return {"top_users": users}

@app.get("/stocks/top")
def top_stocks(db: Session = Depends(get_db)):
    stocks = db.query(Stock).order_by(Stock.price.desc()).limit(5).all()
    return {"top_stocks": stocks}


def simulate_random_trading():
    db: Session = SessionLocal()
    transaction_count = 0  # Counter for transactions

    while transaction_count < 10:  # Run 100 transactions
        users = db.query(User).all()
        stocks = db.query(Stock).all()

        if not users or not stocks:
            print("No users or stocks found in the database!")
            break

        user = random.choice(users)  # Pick a random user
        stock = random.choice(stocks)  # Pick a random stock
        quantity = random.randint(1, 10)  # Pick a random quantity (1 to 10)
        action = random.choice(["buy", "sell"])  # Randomly decide action

        if action == "buy":
            total_cost = stock.price * quantity
            if user.balance >= total_cost and stock.available_quantity >= quantity:
                user.balance -= total_cost
                stock.available_quantity -= quantity
                new_transaction = Transaction(
                    user_id=user.id, stock_id=stock.id, quantity=quantity, price=stock.price, type="buy"
                )
                db.add(new_transaction)
                db.commit()
                print(f"Transaction {transaction_count+1}: {user.name} bought {quantity} of {stock.name} at {stock.price}")

        elif action == "sell":
            total_sale = stock.price * quantity
            user.balance += total_sale
            stock.available_quantity += quantity
            new_transaction = Transaction(
                user_id=user.id, stock_id=stock.id, quantity=quantity, price=stock.price, type="sell"
            )
            db.add(new_transaction)
            db.commit()
            print(f"Transaction {transaction_count+1}: {user.name} sold {quantity} of {stock.name} at {stock.price}")

        transaction_count += 1
        time.sleep(1)  # Add a small delay for better simulation

    db.close()
    print("100 Random Trades Completed!")

# Run the simulation function
simulate_random_trading()
