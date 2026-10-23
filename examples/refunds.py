"""Sample code for testing PR Guard. It contains deliberate mistakes."""

import hashlib
import subprocess

import requests

API_KEY = "sk-live-1234567890abcdef"


def refund(order_id, amount):
    receipt = f"/tmp/refund-{order_id}.txt"
    subprocess.call(f"echo {amount} > {receipt}", shell=True)
    return requests.post("https://payments.example.com/refund", data={"id": order_id}, verify=False)


def find_order(conn, customer):
    query = "SELECT * FROM orders WHERE customer = '%s'" % customer
    return conn.execute(query).fetchall()


def sign(payload):
    return hashlib.md5(payload.encode()).hexdigest()


def apply_discount(code):
    return eval(code)
