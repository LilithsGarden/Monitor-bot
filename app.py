from flask import Flask, request, jsonify
import os
from pi_transfer_script import PiNetworkTransferBot  # Your script

app = Flask(__name__)

@app.route('/transfer', methods=['POST'])
def handle_transfer():
    data = request.get_json()
    access_token = data.get('accessToken')

    if not access_token:
        return jsonify({"error": "No access token"}), 400

    # Set required environment variables
    os.environ['PI_ACCESS_TOKEN'] = access_token
    os.environ['ALLOWED_RECIPIENT_ADDRESS'] = 'pi_1abc234...yourrecipient'
    os.environ['PI_APP_ID'] = 'your_app_id_here'
    os.environ['PI_APP_SECRET'] = 'your_app_secret_here'
    os.environ['PI_SANDBOX_MODE'] = 'true'  # Use sandbox mode for safety

    try:
        bot = PiNetworkTransferBot()
        success = bot.check_and_transfer()
        return jsonify({"success": success}), 200 if success else 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)