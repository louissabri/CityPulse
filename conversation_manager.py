import sqlite3
import json
from datetime import datetime
import hashlib
import os

class ConversationManager:
    def __init__(self, db_path='conversations.db'):
        """Initialize the conversation manager with database path."""
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize the SQLite database with required tables."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Create sessions table for storing conversation history
        c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            conversation_json TEXT
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_conversation(self, session_id):
        """Retrieve conversation history for a session."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('SELECT conversation_json FROM sessions WHERE session_id = ?', (session_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            return json.loads(result[0])
        return []
    
    def save_conversation(self, session_id, conversation):
        """Save the conversation history for a session."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        c.execute('''
        INSERT INTO sessions (session_id, conversation_json, last_activity) 
        VALUES (?, ?, ?) 
        ON CONFLICT(session_id) DO UPDATE SET 
        conversation_json = excluded.conversation_json,
        last_activity = excluded.last_activity
        ''', (session_id, json.dumps(conversation), current_time))
        
        conn.commit()
        conn.close()
    
    def add_message(self, session_id, role, content):
        """Add a message to the conversation history."""
        conversation = self.get_conversation(session_id)
        
        # If this is a new conversation, add system message
        if not conversation:
            conversation = [{
                "role": "system",
                "content": "You are CityPulse, a helpful assistant for finding local information and answering questions about places in Sydney. Provide detailed and helpful responses."
            }]
        
        # Add the new message
        conversation.append({
            "role": role,
            "content": content
        })
        
        # Save the updated conversation
        self.save_conversation(session_id, conversation)
        return conversation
    
    def trim_conversation(self, session_id, max_tokens=3000):
        """Trim conversation to stay under token limits."""
        conversation = self.get_conversation(session_id)
        
        # Always keep the system message if present
        system_message = None
        if conversation and conversation[0]['role'] == 'system':
            system_message = conversation[0]
            conversation = conversation[1:]
        
        # Simple estimation: 4 chars ≈ 1 token
        total_chars = sum(len(msg['content']) for msg in conversation)
        
        # If we're under the limit, return the full conversation
        if total_chars < max_tokens * 4:
            if system_message:
                conversation = [system_message] + conversation
            return conversation
        
        # Otherwise, keep removing oldest messages (after system message)
        while total_chars > max_tokens * 4 and len(conversation) > 2:
            removed = conversation.pop(0)  # Remove oldest message
            total_chars -= len(removed['content'])
        
        # Always include system message at the beginning
        if system_message:
            conversation = [system_message] + conversation
        
        # Save the trimmed conversation
        self.save_conversation(session_id, conversation)
        return conversation
    
    def cleanup_old_sessions(self, days=7):
        """Remove sessions older than specified days to manage disk space."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('DELETE FROM sessions WHERE last_activity < datetime("now", "-? days")', (days,))
        
        deleted_count = conn.total_changes
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def generate_session_id(self, user_ip=None, additional_info=None):
        """Generate a unique session ID."""
        # Combine current time with user info for uniqueness
        base = f"{datetime.now().timestamp()}-{user_ip or 'unknown'}-{additional_info or ''}"
        return hashlib.md5(base.encode()).hexdigest() 