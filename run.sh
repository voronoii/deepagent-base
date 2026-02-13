#!/bin/bash
# Start the DeepAgent backend server
cd /DATA3/users/mj/DeepAgent-Base
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
