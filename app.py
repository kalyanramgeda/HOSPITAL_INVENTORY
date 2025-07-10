from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_cors import CORS
import sqlite3
import os
import datetime

app = Flask(__name__)
app.secret_key = 'Kalyan_ram_geda'
CORS(app)

# ---------------------- Database Setup ----------------------
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            name TEXT NOT NULL
        )
    ''')

    # Items table
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            current_stock INTEGER,
            min_stock INTEGER,
            unit TEXT,
            supplier TEXT,
            last_ordered TIMESTAMP,
            price REAL DEFAULT 0
        )
    ''')

    # Orders table
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            supplier TEXT NOT NULL,
            urgency TEXT CHECK(urgency IN ('low', 'normal', 'high', 'critical')),
            status TEXT CHECK(status IN ('pending', 'approved', 'shipped', 'delivered', 'cancelled')),
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expected_delivery DATE,
            notes TEXT,
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    ''')

    # Settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Transactions table (for movement mock)
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            total_quantity INTEGER,
            total_value REAL,
            transaction_count INTEGER
        )
    ''')

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------- Main Pages ----------------------
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    phone = request.form['phone'].strip()
    name = request.form['name'].strip()

    if not phone.isdigit() or len(phone) != 10:
        flash('Invalid phone number.')
        return redirect(url_for('home'))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE phone=? AND name=?", (phone, name))
    user = c.fetchone()

    if not user:
        c.execute("INSERT INTO users (phone, name) VALUES (?, ?)", (phone, name))
        conn.commit()

    conn.close()
    session['username'] = name
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('home'))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM items")
    total_items = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT category) FROM items")
    category_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM items WHERE current_stock < min_stock")
    low_stock_count = c.fetchone()[0]
    c.execute("SELECT * FROM items ORDER BY id DESC LIMIT 6")
    items = c.fetchall()
    c.execute('''
        SELECT o.*, i.name as item_name, i.unit 
        FROM orders o
        JOIN items i ON o.item_id = i.id
        ORDER BY o.order_date DESC
        LIMIT 4
    ''')
    orders = c.fetchall()
    c.execute('''
        SELECT name, current_stock, min_stock
        FROM items
        WHERE current_stock = 0 OR current_stock < min_stock
        ORDER BY current_stock ASC
        LIMIT 4
    ''')
    alerts = c.fetchall()
    conn.close()

    return render_template('dashboard.html', name=session['username'],
                           total_items=total_items,
                           category_count=category_count,
                           low_stock_count=low_stock_count,
                           items=items, orders=orders, alerts=alerts)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/inventory')
def inventory():
    return render_template('inventory.html')

@app.route('/medical-supplies')
def medical_supplies():
    return render_template('medical_supplies.html')

@app.route('/order')
def order():
    return render_template('order.html')

@app.route('/settings')
def settings():
    return render_template('setting.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

# ---------------------- API: Inventory ----------------------
@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    conn = get_db_connection()
    items = conn.execute('SELECT * FROM items').fetchall()
    conn.close()
    return jsonify([dict(item) for item in items])

@app.route('/api/inventory', methods=['POST'])
def create_inventory_item():
    data = request.get_json()
    required_fields = ['name', 'category', 'current_stock', 'min_stock', 'unit', 'supplier']

    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing fields'}), 400

    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO items (name, category, current_stock, min_stock, unit, supplier)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['name'], data['category'], data['current_stock'],
            data['min_stock'], data['unit'], data['supplier']
        ))
        conn.commit()
        return jsonify({'message': 'Item added successfully'}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/inventory/<int:item_id>', methods=['PUT'])
def update_inventory_item(item_id):
    data = request.get_json()
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE items SET name=?, category=?, current_stock=?, min_stock=?, unit=?, supplier=?
            WHERE id=?
        ''', (
            data['name'], data['category'], data['current_stock'],
            data['min_stock'], data['unit'], data['supplier'], item_id
        ))
        conn.commit()
        return jsonify({'message': 'Item updated'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/inventory/<int:item_id>', methods=['DELETE'])
def delete_inventory_item(item_id):
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
        conn.commit()
        return jsonify({'message': 'Item deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/inventory/<int:item_id>/update-stock', methods=['POST'])
def update_inventory_stock(item_id):
    data = request.get_json()
    action = data.get('action')
    quantity = int(data.get('quantity', 0))

    if action not in ['restock', 'use']:
        return jsonify({'error': 'Invalid action'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT current_stock FROM items WHERE id = ?', (item_id,))
    result = cursor.fetchone()

    if not result:
        return jsonify({'error': 'Item not found'}), 404

    current_stock = result['current_stock']
    new_stock = current_stock + quantity if action == 'restock' else max(0, current_stock - quantity)

    cursor.execute('UPDATE items SET current_stock = ? WHERE id = ?', (new_stock, item_id))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Stock updated'})

# ---------------------- API: Orders ----------------------
@app.route('/api/orders', methods=['GET'])
def get_orders():
    conn = get_db_connection()
    orders = conn.execute('''
        SELECT o.*, i.name as item_name, i.unit 
        FROM orders o
        JOIN items i ON o.item_id = i.id
        ORDER BY o.order_date DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(order) for order in orders])

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    required_fields = ['item_id', 'quantity', 'supplier', 'urgency']

    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO orders (item_id, quantity, supplier, urgency, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['item_id'], data['quantity'], data['supplier'],
            data.get('urgency', 'normal'), 'pending', data.get('notes', '')
        ))
        order_id = cursor.lastrowid
        conn.execute('UPDATE items SET last_ordered = CURRENT_TIMESTAMP WHERE id = ?', (data['item_id'],))
        conn.commit()
        return jsonify({"message": "Order created", "id": order_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/orders/<int:order_id>', methods=['PUT'])
def update_order_status(order_id):
    data = request.get_json()
    if 'status' not in data:
        return jsonify({"error": "Status is required"}), 400

    valid_statuses = ['pending', 'approved', 'shipped', 'delivered', 'cancelled']
    if data['status'] not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400

    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', (data['status'], order_id))
    conn.commit()

    if data['status'] == 'delivered':
        order = conn.execute('SELECT item_id, quantity FROM orders WHERE id = ?', (order_id,)).fetchone()
        conn.execute('UPDATE items SET current_stock = current_stock + ? WHERE id = ?', (order['quantity'], order['item_id']))
        conn.commit()

    conn.close()
    return jsonify({"message": "Order status updated"})

# ---------------------- API: Settings ----------------------
@app.route('/api/settings', methods=['GET'])
def get_settings():
    conn = get_db_connection()
    settings = conn.execute('SELECT * FROM settings').fetchall()
    conn.close()
    return jsonify([{'key': row['key'], 'value': row['value']} for row in settings])

@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.get_json()
    conn = get_db_connection()
    try:
        for key, value in data.items():
            conn.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()
        return jsonify({'message': 'Settings updated successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# ---------------------- API: Analytics ----------------------
@app.route('/api/analytics/summary')
def analytics_summary():
    conn = get_db_connection()
    c = conn.cursor()

    category = request.args.get('category')
    if category:
        c.execute("SELECT COUNT(*) FROM items WHERE category = ?", (category,))
    else:
        c.execute("SELECT COUNT(*) FROM items")
    total_items = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM orders")
    total_orders = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM items WHERE current_stock < min_stock")
    low_stock_items = c.fetchone()[0]

    summary = {
        "total_items": total_items,
        "low_stock_items": low_stock_items,
        "orders_placed": total_orders,
        "inventory_value": 100000,  # Placeholder
        "items_trend": 5,
        "low_stock_trend": -3,
        "orders_trend": 10,
        "value_trend": 7
    }

    conn.close()
    return jsonify(summary)

@app.route('/api/analytics/categories')
def analytics_categories():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT category, COUNT(*) as count FROM items GROUP BY category")
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/analytics/stock-status')
def analytics_stock_status():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM items WHERE current_stock = 0")
    critical_stock = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM items WHERE current_stock < min_stock AND current_stock > 0")
    low_stock = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM items WHERE current_stock >= min_stock")
    good_stock = c.fetchone()[0]
    conn.close()
    return jsonify({
        "critical_stock": critical_stock,
        "low_stock": low_stock,
        "good_stock": good_stock
    })

@app.route('/api/analytics/low-stock')
def analytics_low_stock():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name, category, current_stock, min_stock, supplier FROM items WHERE current_stock < min_stock")
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/analytics/movement')
def analytics_movement():
    today = datetime.date.today()
    mock_data = []
    for i in range(7):
        date = today - datetime.timedelta(days=i)
        mock_data.append({
            "date": date.isoformat(),
            "total_quantity": 50 + i * 5,
            "total_value": 1000 + i * 100,
            "transaction_count": 5 + i
        })
    return jsonify(mock_data)

@app.route('/api/analytics/transactions')
def analytics_transactions():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM transactions ORDER BY date DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

# ---------------------- Main ----------------------
if __name__ == '__main__':
    if not os.path.exists('database.db'):
        init_db()
    else:
        init_db()

    app.run(debug=True, threaded=True)
