# from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
# from main import TechNewsAggregator
# from flask_cors import CORS
# import os
# app = Flask(__name__)
#
# CORS(app)
# app.secret_key = os.urandom(24)
# aggregator = TechNewsAggregator()


# @app.route('/')
# def index():
#     subscribers = aggregator.subscribers
#     return render_template('index.html', subscribers=subscribers)


# @app.route('/subscribe', methods=['POST'])
# def subscribe():
#     email = request.form.get('email')
#     preferences = request.form.getlist('preferences')
#
#     if not email:
#         flash('Email is required!', 'error')
#     else:
#         aggregator.add_subscriber(email, preferences)
#         flash('Successfully subscribed!', 'success')
#
#     return redirect(url_for('index'))
# @app.route('/subscribe', methods=['POST'])
# def subscribe():
#     try:
#         data = request.get_json()  # Parse JSON payload
#         email = data.get('email')
#         preferences = data.get('preferences', [])
#
#         if not email:
#             return jsonify({"message": "Email is required!"}), 400
#
#         # Add the subscriber using the TechNewsAggregator's method
#         aggregator.add_subscriber(email, preferences)
#         return jsonify({"message": "Successfully subscribed!"}), 200
#     except Exception as e:
#         return jsonify({"message": f"Error: {str(e)}"}), 500
#
#
#
# @app.route('/unsubscribe', methods=['POST'])
# def unsubscribe():
#     email = request.form.get('email')
#     if email:
#         aggregator.remove_subscriber(email)
#         flash('Successfully unsubscribed!', 'success')
#     return redirect(url_for('index'))
#
#
# if __name__ == '__main__':
#     app.run(debug=True)
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse,FileResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from main import TechNewsAggregator, SubscriberManager
from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import logging
app = FastAPI()

# CORS Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.secret_key = os.urandom(24)

aggregator = TechNewsAggregator()


class SubscriptionRequest(BaseModel):
    email: str
    preferences: list = []

@app.get("/")
async def index():
    return {"message": "API! 200 OK"}
@app.get("/favicon.ico")
async def favicon():
    return FileResponse(os.path.join("static", "favicon.ico"))

@app.post("/subscribe")
async def subscribe(subscription: SubscriptionRequest):
    try:
        email = subscription.email
        preferences = subscription.preferences

        if not email:
            raise HTTPException(status_code=400, detail="Email is required!")

        aggregator.add_subscriber(email, preferences)
        return JSONResponse(content={"message": "Successfully subscribed!"}, status_code=status.HTTP_200_OK)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# Unsubscribe endpoint
# @app.post("/unsubscribe")
# async def unsubscribe(request: Request):
#     form_data = await request.form()
#     email = form_data.get('email')
#
#     if email:
#         aggregator.remove_subscriber(email)
#         return JSONResponse(content={"message": "Successfully unsubscribed!"}, status_code=status.HTTP_200_OK)
#
#     raise HTTPException(status_code=400, detail="Email is required to unsubscribe")


@app.get("/unsubscribe")
async def unsubscribe_page(token: str):
    try:
        subscriber_manager = SubscriberManager()

        logging.info(f"Received token: {token[:10]}...")

        payload = subscriber_manager.verify_token(token)
        if payload['action'] != 'unsubscribe':
            raise HTTPException(status_code=400, detail="Invalid token type")

        email = payload['email']
        return HTMLResponse(content=f"""
            <html>
                <head>
                    <title>Unsubscribe Confirmation</title>
                    <style>
                        body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; }}
                        .container {{ text-align: center; }}
                        .button {{ display: inline-block; padding: 10px 20px; background-color: #ef4444; color: white; 
                                 text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                        .cancel {{ background-color: #6b7280; margin-left: 10px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Unsubscribe Confirmation</h1>
                        <p>Are you sure you want to unsubscribe {email} from the Tech News newsletter?</p>
                        <form action="/unsubscribe/confirm" method="POST">
                            <input type="hidden" name="token" value="{token}">
                            <button type="submit" class="button">Confirm Unsubscribe</button>
                            <a href="/" class="button cancel">Cancel</a>
                        </form>
                    </div>
                </body>
            </html>
        """)
    except Exception as e:
        logging.error(f"Error in unsubscribe_page: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/unsubscribe/confirm")
async def unsubscribe_confirm(request: Request):
    form_data = await request.form()
    token = form_data.get('token')

    try:
        payload = aggregator.subscriber_manager.verify_token(token)
        if payload['action'] != 'unsubscribe':
            raise HTTPException(status_code=400, detail="Invalid token type")

        aggregator.remove_subscriber(payload['email'])

        return HTMLResponse(content="""
            <html>
                <head>
                    <title>Unsubscribed Successfully</title>
                    <style>
                        body { font-family: -apple-system, system-ui, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; }
                        .container { text-align: center; }
                        .message { color: #059669; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1 class="message">Successfully Unsubscribed</h1>
                        <p>You have been unsubscribed from the Tech News newsletter.</p>
                        <p>We're sorry to see you go! You can always subscribe again from our homepage.</p>
                    </div>
                </body>
            </html>
        """)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/preferences")
async def preferences_page(token: str):
    try:
        payload = aggregator.subscriber_manager.verify_token(token)
        if payload['action'] != 'preferences':
            raise HTTPException(status_code=400, detail="Invalid token type")

        email = payload['email']
        current_preferences = aggregator.subscribers.get(email, [])

        sources_html = ""
        for source in [
            'Hacker News', 'Reddit Tech', 'Dev.to', 'GitHub Trending',
            'Stack Exchange', 'The Verge', 'Wired', 'Ars Technica',
            'VentureBeat', 'ZDNet', 'TechRadar', 'Hackernoon'
        ]:
            checked = "checked" if source in current_preferences else ""
            sources_html += f"""
                <div class="preference-item">
                    <input type="checkbox" id="{source}" name="preferences" value="{source}" {checked}>
                    <label for="{source}">{source}</label>
                </div>
            """

        return HTMLResponse(content=f"""
            <html>
                <head>
                    <title>Manage Newsletter Preferences</title>
                    <style>
                        body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; }}
                        .container {{ text-align: center; }}
                        .preferences-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); 
                                          gap: 10px; text-align: left; margin: 20px 0; }}
                        .preference-item {{ padding: 10px; }}
                        .button {{ display: inline-block; padding: 10px 20px; background-color: #2563eb; color: white; 
                                 text-decoration: none; border-radius: 5px; border: none; cursor: pointer; }}
                        .email-display {{ color: #6b7280; font-size: 0.9em; margin: 10px 0; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Manage Newsletter Preferences</h1>
                        <p class="email-display">Email: {email}</p>
                        <form action="/preferences/update" method="POST">
                            <input type="hidden" name="token" value="{token}">
                            <div class="preferences-grid">
                                {sources_html}
                            </div>
                            <button type="submit" class="button">Update Preferences</button>
                        </form>
                    </div>
                </body>
            </html>
        """)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/preferences/update")
async def update_preferences(request: Request):
    form_data = await request.form()
    token = form_data.get('token')
    new_preferences = form_data.getlist('preferences')

    try:
        payload = aggregator.subscriber_manager.verify_token(token)
        if payload['action'] != 'preferences':
            raise HTTPException(status_code=400, detail="Invalid token type")

        email = payload['email']
        if email in aggregator.subscribers:
            aggregator.subscribers[email] = new_preferences
            aggregator.save_subscribers()

            return HTMLResponse(content="""
                <html>
                    <head>
                        <title>Preferences Updated</title>
                        <style>
                            body { font-family: -apple-system, system-ui, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; }
                            .container { text-align: center; }
                            .message { color: #059669; }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1 class="message">Preferences Updated Successfully</h1>
                            <p>Your newsletter preferences have been updated.</p>
                            <p>You'll receive your next newsletter with your new preferences.</p>
                        </div>
                    </body>
                </html>
            """)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
