import streamlit as st

# Simple Streamlit App
st.title("🚀 Streamlit Deployment Test")
st.write("If you see this message, your Streamlit app is working correctly on Streamlit Cloud!")

# Basic user input to test interaction
name = st.text_input("Enter your name:")
if name:
    st.success(f"Hello, {name}! 🎉")

# Display system information
import platform
st.write("Running on:", platform.system(), platform.release())
