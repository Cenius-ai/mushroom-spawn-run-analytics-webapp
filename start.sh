# Mushroom Spawn Run Analytics - run command
#
# Starts the Streamlit server in the foreground on 0.0.0.0:8501 (the port the
# Streamlit runner uses). Nothing is installed here; run ./install.sh first.

streamlit run streamlit_app.py \
  --server.address=0.0.0.0 \
  --server.port=8501 \
  --server.headless=true
