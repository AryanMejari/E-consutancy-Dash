# app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import json
from datetime import datetime
import google.generativeai as genai
import PyPDF2
import docx
import tempfile

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure Gemini API
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))

# In-memory storage for demo purposes (use a database in production)
user_submissions = []
analyzed_comments = []

# Initialize the generative model
model = genai.GenerativeModel('gemini-pro')

def extract_text_from_pdf(file_path):
    """Extract text from PDF file"""
    text = ""
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def extract_text_from_docx(file_path):
    """Extract text from DOCX file"""
    doc = docx.Document(file_path)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

def analyze_text_with_gemini(text, clause, user_info):
    """Analyze the submitted text using Gemini API"""
    # Create a JSON template string first
    json_template = '''{
        "sentiment": "positive/negative/neutral",
        "sentiment_score": 0.0,
        "key_phrases": ["phrase1", "phrase2", "phrase3"],
        "suggested_action": "text describing suggested action",
        "impact": "High/Medium/Low",
        "relevance": "Very Relevant/Relevant/General",
        "summary": "brief summary of the feedback",
        "is_actionable": true/false,
        "stakeholder_type": "Individual/Organization/Industry Body"
    }'''
    
    prompt = f"""
    Analyze this public consultation feedback for a policy document and provide insights in JSON format.
    
    User Information: {user_info}
    Related Clause: {clause}
    Feedback Text: {text}
    
    Please provide analysis with the following structure:
    {json_template}
    """
    
    try:
        response = model.generate_content(prompt)
        # Extract JSON from the response
        response_text = response.text
        # Remove markdown code blocks if present
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        analysis = json.loads(response_text)
        return analysis
    except Exception as e:
        print(f"Error analyzing text with Gemini: {e}")
        # Return a default analysis in case of error
        return {
            "sentiment": "neutral",
            "sentiment_score": 0.0,
            "key_phrases": [],
            "suggested_action": "No specific action suggested",
            "impact": "Low",
            "relevance": "General",
            "summary": "Analysis unavailable",
            "is_actionable": False,
            "stakeholder_type": "Individual"
        }
@app.route('/')
def serve_frontend():
    """Serve the frontend HTML file"""
    return send_from_directory('.', 'seconddemo.html')

@app.route('/api/submit-feedback', methods=['POST'])
def submit_feedback():
    """Handle user feedback submission"""
    try:
        data = request.form
        files = request.files
        
        # Extract user info
        user_info = {
            'name': data.get('name'),
            'organization': data.get('organization', ''),
            'email': data.get('email')
        }
        
        # Extract feedback details
        clause = data.get('clause')
        comment_text = data.get('comment')
        
        # Process uploaded files if any
        uploaded_text = ""
        if 'files' in files:
            for file in files.getlist('files'):
                # Save file temporarily
                temp_dir = tempfile.gettempdir()
                file_path = os.path.join(temp_dir, file.filename)
                file.save(file_path)
                
                # Extract text based on file type
                if file.filename.lower().endswith('.pdf'):
                    uploaded_text += extract_text_from_pdf(file_path) + "\n\n"
                elif file.filename.lower().endswith(('.doc', '.docx')):
                    uploaded_text += extract_text_from_docx(file_path) + "\n\n"
                
                # Clean up temporary file
                os.remove(file_path)
        
        # Combine comment text and uploaded file text
        full_text = comment_text + "\n\n" + uploaded_text if uploaded_text else comment_text
        
        # Analyze the text using Gemini API
        analysis = analyze_text_with_gemini(full_text, clause, user_info)
        
        # Create submission record
        submission_id = str(uuid.uuid4())
        submission = {
            'id': submission_id,
            'user_info': user_info,
            'clause': clause,
            'text': full_text,
            'analysis': analysis,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'status': 'submitted'
        }
        
        # Store submission
        user_submissions.append(submission)
        
        # Also add to analyzed comments for admin dashboard
        analyzed_comment = {
            'id': len(analyzed_comments) + 1,
            'source': f"{user_info['name']} ({user_info['organization']})" if user_info['organization'] else user_info['name'],
            'isKeyStakeholder': user_info['organization'] != '',  # Assume organizations are key stakeholders
            'sentiment': analysis['sentiment'],
            'clause': clause,
            'text': full_text[:500] + "..." if len(full_text) > 500 else full_text,  # Truncate for display
            'type': "actionable" if analysis['is_actionable'] else "comment",
            'campaign': False,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'analysis': analysis
        }
        analyzed_comments.append(analyzed_comment)
        
        return jsonify({
            'success': True,
            'submission_id': submission_id,
            'analysis': analysis
        })
        
    except Exception as e:
        print(f"Error processing submission: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/user-submissions/<email>')
def get_user_submissions(email):
    """Get all submissions for a specific user"""
    user_subs = [s for s in user_submissions if s['user_info']['email'] == email]
    return jsonify(user_subs)

@app.route('/api/analytics/comments')
def get_analyzed_comments():
    """Get all analyzed comments for the admin dashboard"""
    return jsonify(analyzed_comments)

@app.route('/api/analytics/summary')
def get_analytics_summary():
    """Get analytics summary for the admin dashboard"""
    total_comments = len(analyzed_comments)
    key_stakeholders = len([c for c in analyzed_comments if c['isKeyStakeholder']])
    actionable_suggestions = len([c for c in analyzed_comments if c['type'] == 'actionable'])
    
    # Sentiment distribution
    sentiments = [c['sentiment'] for c in analyzed_comments]
    positive = sentiments.count('positive')
    negative = sentiments.count('negative')
    neutral = sentiments.count('neutral')
    
    # Stakeholder type distribution
    stakeholder_types = [c['analysis'].get('stakeholder_type', 'Individual') for c in analyzed_comments]
    stakeholder_distribution = {
        'Industry Associations': stakeholder_types.count('Industry Body'),
        'Corporate Bodies': stakeholder_types.count('Organization'),
        'Individual Citizens': stakeholder_types.count('Individual'),
        'Other': len(stakeholder_types) - (
            stakeholder_types.count('Industry Body') + 
            stakeholder_types.count('Organization') + 
            stakeholder_types.count('Individual')
        )
    }
    
    # Top concerns (from negative comments)
    negative_comments = [c for c in analyzed_comments if c['sentiment'] == 'negative']
    
    summary = {
        'total_comments': total_comments,
        'key_stakeholders': key_stakeholders,
        'actionable_suggestions': actionable_suggestions,
        'coordinated_campaigns': 0,  # This would require more advanced analysis
        'sentiment_distribution': {
            'positive': positive,
            'negative': negative,
            'neutral': neutral
        },
        'stakeholder_distribution': stakeholder_distribution,
        'top_concerns': [
            "Compliance costs for smaller companies",
            "Reporting timeline too aggressive",
            "Lack of clarity in audit requirements"
        ] if negative_comments else []
    }
    
    return jsonify(summary)

if __name__ == '__main__':
    # Load sample data for demo
    sample_comments = [
        {
            'id': 1,
            'source': "Institute of Chartered Accountants of India (ICAI)",
            'isKeyStakeholder': True,
            'sentiment': "negative",
            'clause': "Clause 7: Corporate Social Responsibility (CSR) Reporting Requirements",
            'text': "While the intention to enhance transparency in CSR spending is commendable, the proposed amendment may create unintended compliance burdens for smaller companies...",
            'type': "actionable",
            'campaign': False,
            'date': "2023-02-15",
            'analysis': {
                'sentiment_score': -0.8,
                'key_phrases': ["compliance burdens", "smaller companies", "mandatory disclosure requirements"],
                'suggested_action': "Consider threshold-based application of disclosure requirements",
                'impact': "High",
                'relevance': "Very Relevant",
                'summary': "Concerned about compliance burden on smaller companies",
                'is_actionable': True,
                'stakeholder_type': "Industry Body"
            }
        }
    ]
    analyzed_comments.extend(sample_comments)
    
    app.run(debug=True, port=5000)