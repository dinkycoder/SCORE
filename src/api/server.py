from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'SCORE', 'version': '0.1.0'}), 200

@app.route('/model-version', methods=['GET'])
def model_version():
    return jsonify({
        'model_version': '1.0.0',
        'validation_auc_roc': 0.8658
    }), 200

@app.route('/score/<wallet_address>', methods=['GET'])
def score_wallet(wallet_address: str):
    if not wallet_address.startswith('0x') or len(wallet_address) != 42:
        return jsonify({'error': 'Invalid wallet address'}), 400
    
    return jsonify({
        'wallet': wallet_address,
        'pd': 0.35,
        'lgd': 0.28,
        'ead': 5000.0,
        'credit_score': 0.72,
        'recommendation': 'monitor'
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
