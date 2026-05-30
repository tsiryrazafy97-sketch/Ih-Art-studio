from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
import os
import json
import uuid
from functools import wraps

app = Flask(__name__)
app.secret_key = 'fahstudio_secret_key_2025_secure'
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Charger les traductions
try:
    with open('langue.json', 'r', encoding='utf-8') as f:
        TRADUCTIONS = json.load(f)
except FileNotFoundError:
    TRADUCTIONS = {
        "fr": {"slogan": "Salon d'esthétique · Onglerie · Coiffure · Massage"},
        "mg": {"slogan": "Salon d'esthétique · Onglerie · Coiffure · Massage"}
    }

ADMIN_CODE = "FAHSTUDIO2025"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'avi', 'webm', 'pdf', 'doc', 'docx', 'txt'}

# Fitehirizana ny appel active
appels_en_cours = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_lang():
    return session.get('lang', 'fr')

def t(key):
    """Fonction de traduction - utilisable dans tous les templates"""
    lang = get_lang()
    return TRADUCTIONS.get(lang, {}).get(key, key)

def get_or_create_conversation(user1_id, user2_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id FROM conversations 
        WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)
    """, (user1_id, user2_id, user2_id, user1_id))
    
    conv = cursor.fetchone()
    
    if conv:
        conn.close()
        return conv['id']
    else:
        cursor.execute("""
            INSERT INTO conversations (user1_id, user2_id, last_message, last_message_date)
            VALUES (?, ?, ?, ?)
        """, (user1_id, user2_id, '', datetime.now()))
        conn.commit()
        conv_id = cursor.lastrowid
        conn.close()
        return conv_id

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            date_naissance DATE NOT NULL,
            sexe TEXT NOT NULL,
            email TEXT UNIQUE,
            telephone TEXT UNIQUE,
            mot_de_passe TEXT NOT NULL,
            photo_profil TEXT,
            is_admin INTEGER DEFAULT 0,
            en_ligne INTEGER DEFAULT 0,
            derniere_activite TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_inscription TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titre TEXT,
            description TEXT NOT NULL,
            categorie TEXT NOT NULL,
            type TEXT NOT NULL,
            fichier TEXT,
            lien_video TEXT,
            date_publication TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commentaires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publication_id INTEGER,
            user_id INTEGER,
            parent_id INTEGER DEFAULT NULL,
            texte TEXT NOT NULL,
            date_commentaire TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (publication_id) REFERENCES publications(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (parent_id) REFERENCES commentaires(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publication_id INTEGER,
            user_id INTEGER,
            type TEXT DEFAULT 'like',
            date_reaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (publication_id) REFERENCES publications(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(publication_id, user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reaction_commentaires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commentaire_id INTEGER,
            user_id INTEGER,
            date_reaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (commentaire_id) REFERENCES commentaires(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(commentaire_id, user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER,
            user2_id INTEGER,
            last_message TEXT,
            last_message_date TIMESTAMP,
            FOREIGN KEY (user1_id) REFERENCES users(id),
            FOREIGN KEY (user2_id) REFERENCES users(id),
            UNIQUE(user1_id, user2_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            expediteur_id INTEGER,
            destinataire_id INTEGER,
            contenu TEXT,
            fichier TEXT,
            type_fichier TEXT,
            lu INTEGER DEFAULT 0,
            date_envoi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id),
            FOREIGN KEY (expediteur_id) REFERENCES users(id),
            FOREIGN KEY (destinataire_id) REFERENCES users(id)
        )
    ''')
    
    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_destinataire ON messages(destinataire_id, lu)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_commentaires_publication ON commentaires(publication_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_users ON conversations(user1_id, user2_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_en_ligne ON users(en_ligne)")
    
    admin_email = "admin@fahstudio.com"
    cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
    if not cursor.fetchone():
        admin_password = generate_password_hash("admin123")
        cursor.execute("""
            INSERT INTO users (nom, date_naissance, sexe, email, mot_de_passe, is_admin)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('Administrateur', '2000-01-01', 'homme', admin_email, admin_password, 1))
    
    conn.commit()
    conn.close()
    print("✅ Base de données initialisée avec succès!")

# ==================== MIDDLEWARE ====================

@app.before_request
def set_default_lang():
    if 'lang' not in session:
        session['lang'] = 'fr'
    if 'theme' not in session:
        session['theme'] = 'dark'
    if 'user_id' in session:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET derniere_activite = CURRENT_TIMESTAMP, en_ligne = 1 WHERE id = ?", (session['user_id'],))
        conn.commit()
        conn.close()

@app.context_processor
def inject_t():
    return dict(t=t)

# ==================== ROUTES LANGUE ET THEME ====================

@app.route('/changer-langue', methods=['POST'])
def changer_langue():
    langue = request.form.get('langue', 'fr')
    session['lang'] = langue
    flash(f'Langue changée en {langue}', 'success')
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect('/')

@app.route('/changer-theme', methods=['POST'])
def changer_theme():
    theme = request.form.get('theme', 'dark')
    session['theme'] = theme
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect('/')

# ==================== DECORATEURS ====================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Accès réservé à l\'administrateur', 'danger')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

# ==================== ROUTES PRINCIPALES ====================

@app.route('/')
def index():
    return render_template('index.html', t=t)

@app.route('/recherche')
def recherche():
    query = request.args.get('q', '')
    source = request.args.get('source', 'both')
    site_results = []
    internet_results = []
    
    if query:
        if source in ['both', 'site']:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM publications 
                WHERE description LIKE ? OR titre LIKE ?
                ORDER BY date_publication DESC
            """, (f'%{query}%', f'%{query}%'))
            results = cursor.fetchall()
            site_results = [dict(r) for r in results]
            conn.close()
        
        if source in ['both', 'internet']:
            internet_results = [
                {'title': f'Top tendances mode "{query}" 2025', 
                 'url': f'https://www.google.com/search?q=mode+{query}', 
                 'snippet': f'Découvrez les dernières tendances en matière de {query}'},
                {'title': f'Pinterest: Idées créatives pour {query}', 
                 'url': f'https://www.pinterest.com/search/pins/?q={query}', 
                 'snippet': f'Inspiration et tutoriels pour {query}'},
                {'title': f'YouTube: Tutoriel {query} pas à pas', 
                 'url': f'https://www.youtube.com/results?search_query=tutoriel+{query}', 
                 'snippet': f'Apprenez à réaliser un magnifique {query}'}
            ]
    
    return render_template('recherche.html', query=query, source=source, 
                         site_results=site_results, internet_results=internet_results, t=t)

@app.route('/publications')
def publications():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM publications ORDER BY date_publication DESC")
    publications = cursor.fetchall()
    
    publications_list = []
    for pub in publications:
        pub_dict = dict(pub)
        
        cursor.execute("SELECT COUNT(*) as count FROM reactions WHERE publication_id=?", (pub['id'],))
        pub_dict['nb_reactions'] = cursor.fetchone()['count']
        
        cursor.execute("""
            SELECT c.*, u.nom as user_nom, u.photo_profil as user_photo
            FROM commentaires c 
            JOIN users u ON c.user_id = u.id 
            WHERE c.publication_id=? 
            ORDER BY c.date_commentaire ASC
        """, (pub['id'],))
        commentaires = cursor.fetchall()
        
        commentaires_dict = {}
        for cmt in commentaires:
            cmt_dict = dict(cmt)
            cursor.execute("SELECT COUNT(*) as count FROM reaction_commentaires WHERE commentaire_id=?", (cmt['id'],))
            cmt_dict['nb_coeurs'] = cursor.fetchone()['count']
            if session.get('user_id'):
                cursor.execute("SELECT id FROM reaction_commentaires WHERE commentaire_id=? AND user_id=?", 
                             (cmt['id'], session['user_id']))
                cmt_dict['user_a_reagi'] = cursor.fetchone() is not None
            else:
                cmt_dict['user_a_reagi'] = False
            cmt_dict['reponses'] = []
            commentaires_dict[cmt_dict['id']] = cmt_dict
        
        commentaires_racine = []
        for cmt_id, cmt in commentaires_dict.items():
            if cmt['parent_id'] is None:
                commentaires_racine.append(cmt)
            else:
                if cmt['parent_id'] in commentaires_dict:
                    commentaires_dict[cmt['parent_id']]['reponses'].append(cmt)
        
        pub_dict['commentaires'] = commentaires_racine
        
        if session.get('user_id'):
            cursor.execute("SELECT id FROM reactions WHERE publication_id=? AND user_id=?", 
                         (pub['id'], session['user_id']))
            pub_dict['user_a_reagi'] = cursor.fetchone() is not None
        else:
            pub_dict['user_a_reagi'] = False
        
        publications_list.append(pub_dict)
    
    conn.close()
    return render_template('publications.html', publications=publications_list, t=t)

@app.route('/videos')
def videos():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM publications WHERE type IN ('video', 'lien') ORDER BY date_publication DESC")
    videos = cursor.fetchall()
    
    videos_list = []
    for video in videos:
        video_dict = dict(video)
        cursor.execute("SELECT COUNT(*) as count FROM reactions WHERE publication_id=?", (video['id'],))
        video_dict['nb_reactions'] = cursor.fetchone()['count']
        videos_list.append(video_dict)
    
    conn.close()
    return render_template('videos.html', videos=videos_list, t=t)

# ==================== AUTHENTIFICATION ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nom = request.form['nom']
        date_naissance = request.form['date_naissance']
        sexe = request.form['sexe']
        contact = request.form['contact']
        mot_de_passe = generate_password_hash(request.form['mot_de_passe'])
        
        conn = get_db()
        cursor = conn.cursor()
        
        if '@' in contact:
            cursor.execute("SELECT id FROM users WHERE email = ?", (contact,))
        else:
            cursor.execute("SELECT id FROM users WHERE telephone = ?", (contact,))
        
        if cursor.fetchone():
            flash('Cet email ou numéro est déjà utilisé!', 'danger')
            return redirect('/register')
        
        cursor.execute("""
            INSERT INTO users (nom, date_naissance, sexe, email, telephone, mot_de_passe, is_admin)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (nom, date_naissance, sexe, 
              contact if '@' in contact else None, 
              contact if '@' not in contact else None, 
              mot_de_passe))
        conn.commit()
        conn.close()
        
        flash('Inscription réussie!', 'success')
        return redirect('/login')
    
    return render_template('register.html', t=t)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        contact = request.form['contact']
        mot_de_passe = request.form['mot_de_passe']
        
        conn = get_db()
        cursor = conn.cursor()
        
        if '@' in contact:
            cursor.execute("SELECT * FROM users WHERE email = ?", (contact,))
        else:
            cursor.execute("SELECT * FROM users WHERE telephone = ?", (contact,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['mot_de_passe'], mot_de_passe):
            session['user_id'] = user['id']
            session['user_nom'] = user['nom']
            session['is_admin'] = user['is_admin'] == 1
            
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET en_ligne = 1, derniere_activite = CURRENT_TIMESTAMP WHERE id = ?", (session['user_id'],))
            conn.commit()
            conn.close()
            
            if session['is_admin']:
                flash(f'Bienvenue Administrateur {user["nom"]}!', 'success')
            else:
                flash(f'Bienvenue {user["nom"]}!', 'success')
            return redirect('/')
        else:
            flash('Email/numéro ou mot de passe incorrect', 'danger')
    
    return render_template('login.html', t=t)

@app.route('/logout')
def logout():
    if 'user_id' in session:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET en_ligne = 0 WHERE id = ?", (session['user_id'],))
        conn.commit()
        conn.close()
    
    session.clear()
    flash('Déconnecté avec succès!', 'success')
    return redirect('/')

# ==================== PROFIL UTILISATEUR ====================

@app.route('/modifier-profil', methods=['GET', 'POST'])
def modifier_profil():
    if 'user_id' not in session:
        flash('Veuillez vous connecter d\'abord.', 'warning')
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        nom = request.form.get('nom')
        date_naissance = request.form.get('date_naissance')
        sexe = request.form.get('sexe')
        email = request.form.get('email')
        telephone = request.form.get('telephone')
        ancien_mdp = request.form.get('ancien_mot_de_passe')
        nouveau_mdp = request.form.get('nouveau_mot_de_passe')
        
        cursor.execute("SELECT mot_de_passe FROM users WHERE id = ?", (session['user_id'],))
        user = cursor.fetchone()
        
        if ancien_mdp and nouveau_mdp:
            if not check_password_hash(user['mot_de_passe'], ancien_mdp):
                flash('Ancien mot de passe incorrect!', 'danger')
                return redirect('/modifier-profil')
            nouveau_mdp_hash = generate_password_hash(nouveau_mdp)
            cursor.execute("UPDATE users SET mot_de_passe = ? WHERE id = ?", (nouveau_mdp_hash, session['user_id']))
            flash('Mot de passe mis à jour!', 'success')
        
        cursor.execute("""
            UPDATE users 
            SET nom = ?, date_naissance = ?, sexe = ?, email = ?, telephone = ?
            WHERE id = ?
        """, (nom, date_naissance, sexe, email, telephone, session['user_id']))
        conn.commit()
        
        session['user_nom'] = nom
        flash('Profil mis à jour avec succès!', 'success')
        return redirect('/mon-compte')
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()
    user_dict = dict(user) if user else {}
    conn.close()
    
    return render_template('modifier_profil.html', user=user_dict, t=t)

@app.route('/mon-compte', methods=['GET', 'POST'])
def mon_compte():
    if 'user_id' not in session:
        flash('Veuillez vous connecter d\'abord.', 'warning')
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST' and 'photo_profil' in request.files:
        file = request.files['photo_profil']
        if file and allowed_file(file.filename):
            extension = file.filename.rsplit('.', 1)[1].lower()
            nouveau_nom = f"user_{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"
            chemin = os.path.join(app.config['UPLOAD_FOLDER'], 'profils', nouveau_nom)
            os.makedirs(os.path.dirname(chemin), exist_ok=True)
            file.save(chemin)
            cursor.execute("UPDATE users SET photo_profil = ? WHERE id = ?", 
                         (f"uploads/profils/{nouveau_nom}", session['user_id']))
            conn.commit()
            flash('Photo de profil mise à jour!', 'success')
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()
    user_dict = dict(user) if user else {}
    
    cursor.execute("SELECT COUNT(*) as count FROM reactions WHERE user_id = ?", (session['user_id'],))
    nb_reactions = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM commentaires WHERE user_id = ?", (session['user_id'],))
    nb_commentaires = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        WHERE (c.user1_id = ? OR c.user2_id = ?) AND m.destinataire_id = ? AND m.lu = 0
    """, (session['user_id'], session['user_id'], session['user_id']))
    nb_messages_non_lus = cursor.fetchone()['count']
    
    conn.close()
    return render_template('mon_compte.html', user=user_dict, 
                         nb_reactions=nb_reactions, nb_commentaires=nb_commentaires,
                         nb_messages_non_lus=nb_messages_non_lus, t=t)

# ==================== MESSAGERIE ====================

@app.route('/messages')
def messages():
    if 'user_id' not in session:
        flash('Veuillez vous connecter', 'warning')
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.*,
               CASE 
                   WHEN c.user1_id = ? THEN u2.nom
                   ELSE u1.nom
               END as autre_nom,
               CASE 
                   WHEN c.user1_id = ? THEN u2.photo_profil
                   ELSE u1.photo_profil
               END as autre_photo,
               CASE 
                   WHEN c.user1_id = ? THEN u2.id
                   ELSE u1.id
               END as autre_id,
               CASE 
                   WHEN c.user1_id = ? THEN u2.en_ligne
                   ELSE u1.en_ligne
               END as autre_en_ligne,
               (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id AND destinataire_id = ? AND lu = 0) as non_lus
        FROM conversations c
        JOIN users u1 ON c.user1_id = u1.id
        JOIN users u2 ON c.user2_id = u2.id
        WHERE c.user1_id = ? OR c.user2_id = ?
        ORDER BY c.last_message_date DESC
    """, (session['user_id'], session['user_id'], session['user_id'], session['user_id'], session['user_id'], session['user_id'], session['user_id']))
    
    conversations = cursor.fetchall()
    conversations_list = [dict(c) for c in conversations]
    conn.close()
    
    return render_template('messages.html', conversations=conversations_list, t=t)

@app.route('/conversation/<int:user_id>')
def conversation(user_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, nom, photo_profil, en_ligne FROM users WHERE id = ?", (user_id,))
    autre = cursor.fetchone()
    
    if not autre:
        flash('Utilisateur non trouvé', 'danger')
        return redirect('/messages')
    
    conv_id = get_or_create_conversation(session['user_id'], user_id)
    
    cursor.execute("""
        UPDATE messages SET lu = 1 
        WHERE conversation_id = ? AND destinataire_id = ?
    """, (conv_id, session['user_id']))
    conn.commit()
    
    cursor.execute("""
        SELECT m.*, u.nom as expediteur_nom, u.photo_profil as expediteur_photo
        FROM messages m
        JOIN users u ON m.expediteur_id = u.id
        WHERE m.conversation_id = ?
        ORDER BY m.date_envoi ASC
    """, (conv_id,))
    messages_list = cursor.fetchall()
    
    conn.close()
    
    return render_template('conversation.html', autre=dict(autre), messages=messages_list, t=t)

@app.route('/api/envoyer-message', methods=['POST'])
def api_envoyer_message():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    destinataire_id = request.form.get('destinataire_id')
    contenu = request.form.get('contenu', '')
    
    fichier = None
    type_fichier = None
    
    if 'fichier' in request.files:
        file = request.files['fichier']
        if file and allowed_file(file.filename):
            extension = file.filename.rsplit('.', 1)[1].lower()
            nouveau_nom = f"msg_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{session['user_id']}.{extension}"
            chemin = os.path.join(app.config['UPLOAD_FOLDER'], 'messages', nouveau_nom)
            os.makedirs(os.path.dirname(chemin), exist_ok=True)
            file.save(chemin)
            fichier = f"uploads/messages/{nouveau_nom}"
            
            if extension in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                type_fichier = 'image'
            elif extension in ['mp4', 'mov', 'avi', 'webm']:
                type_fichier = 'video'
            else:
                type_fichier = 'fichier'
    
    if not contenu and not fichier:
        return jsonify({'error': 'Message vide'}), 400
    
    conv_id = get_or_create_conversation(session['user_id'], int(destinataire_id))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO messages (conversation_id, expediteur_id, destinataire_id, contenu, fichier, type_fichier)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (conv_id, session['user_id'], destinataire_id, contenu, fichier, type_fichier))
    
    message_id = cursor.lastrowid
    
    cursor.execute("""
        UPDATE conversations 
        SET last_message = ?, last_message_date = ?
        WHERE id = ?
    """, (contenu[:100] if contenu else '[Fichier envoyé]', datetime.now(), conv_id))
    
    conn.commit()
    
    cursor.execute("""
        SELECT m.*, u.nom as expediteur_nom, u.photo_profil as expediteur_photo
        FROM messages m
        JOIN users u ON m.expediteur_id = u.id
        WHERE m.id = ?
    """, (message_id,))
    nouveau_message = cursor.fetchone()
    
    conn.close()
    
    return jsonify({
        'success': True,
        'message': {
            'id': nouveau_message['id'],
            'contenu': nouveau_message['contenu'],
            'fichier': nouveau_message['fichier'],
            'type_fichier': nouveau_message['type_fichier'],
            'date_envoi': nouveau_message['date_envoi'],
            'expediteur_nom': nouveau_message['expediteur_nom'],
            'expediteur_id': nouveau_message['expediteur_id'],
            'expediteur_photo': nouveau_message['expediteur_photo']
        }
    })

@app.route('/api/get-messages/<int:user_id>')
def api_get_messages(user_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    last_id = request.args.get('last_id', 0, type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id FROM conversations 
        WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)
    """, (session['user_id'], user_id, user_id, session['user_id']))
    conv = cursor.fetchone()
    
    if not conv:
        conn.close()
        return jsonify({'messages': []})
    
    cursor.execute("""
        UPDATE messages SET lu = 1 
        WHERE conversation_id = ? AND destinataire_id = ? AND lu = 0
    """, (conv['id'], session['user_id']))
    conn.commit()
    
    cursor.execute("""
        SELECT m.*, u.nom as expediteur_nom, u.photo_profil as expediteur_photo
        FROM messages m
        JOIN users u ON m.expediteur_id = u.id
        WHERE m.conversation_id = ? AND m.id > ?
        ORDER BY m.date_envoi ASC
    """, (conv['id'], last_id))
    messages = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'messages': [dict(m) for m in messages]
    })

@app.route('/supprimer-conversation/<int:user_id>', methods=['POST'])
def supprimer_conversation(user_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id FROM conversations 
        WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)
    """, (session['user_id'], user_id, user_id, session['user_id']))
    
    conv = cursor.fetchone()
    
    if conv:
        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conv['id'],))
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conv['id'],))
        conn.commit()
        flash('Conversation supprimée!', 'success')
    
    conn.close()
    return redirect('/messages')

@app.route('/messages/nouveau', methods=['GET', 'POST'])
def nouveau_message():
    if 'user_id' not in session:
        return redirect('/login')
    
    if request.method == 'POST':
        destinataire_id = request.form.get('destinataire_id')
        contenu = request.form.get('contenu')
        fichier = request.files.get('fichier')
        
        if not destinataire_id:
            flash('Veuillez sélectionner un destinataire!', 'danger')
            return redirect('/messages/nouveau')
        
        fichier_path = None
        type_fichier = None
        
        if fichier and allowed_file(fichier.filename):
            extension = fichier.filename.rsplit('.', 1)[1].lower()
            nouveau_nom = f"msg_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{session['user_id']}.{extension}"
            chemin = os.path.join(app.config['UPLOAD_FOLDER'], 'messages', nouveau_nom)
            os.makedirs(os.path.dirname(chemin), exist_ok=True)
            fichier.save(chemin)
            fichier_path = f"uploads/messages/{nouveau_nom}"
            
            if extension in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                type_fichier = 'image'
            elif extension in ['mp4', 'mov', 'avi', 'webm']:
                type_fichier = 'video'
            else:
                type_fichier = 'fichier'
        
        if not contenu and not fichier_path:
            flash('Message vide!', 'danger')
            return redirect('/messages/nouveau')
        
        conv_id = get_or_create_conversation(session['user_id'], int(destinataire_id))
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (conversation_id, expediteur_id, destinataire_id, contenu, fichier, type_fichier)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (conv_id, session['user_id'], destinataire_id, contenu, fichier_path, type_fichier))
        
        cursor.execute("""
            UPDATE conversations 
            SET last_message = ?, last_message_date = ?
            WHERE id = ?
        """, (contenu[:100] if contenu else '[Fichier envoyé]', datetime.now(), conv_id))
        
        conn.commit()
        conn.close()
        
        flash('Message envoyé!', 'success')
        return redirect('/conversation/' + destinataire_id)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nom, photo_profil, en_ligne 
        FROM users 
        WHERE id != ? 
        ORDER BY en_ligne DESC, nom ASC
    """, (session['user_id'],))
    users = cursor.fetchall()
    conn.close()
    
    return render_template('nouveau_message.html', users=users, t=t)

# ==================== API STATUS EN LIGNE ====================

@app.route('/api/status-en-ligne')
def api_status_en_ligne():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({'error': 'ID requis'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT en_ligne, derniere_activite FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    en_ligne = False
    if user:
        en_ligne = user['en_ligne'] == 1
        if user['derniere_activite']:
            try:
                derniere = datetime.strptime(user['derniere_activite'], '%Y-%m-%d %H:%M:%S')
                if (datetime.now() - derniere).seconds > 120:
                    en_ligne = False
            except:
                pass
    
    return jsonify({'en_ligne': en_ligne})

# ==================== APPEL VIDEO/VOCAL ====================

@app.route('/api/appel/initier', methods=['POST'])
def initier_appel():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    destinataire_id = data.get('destinataire_id')
    type_appel = data.get('type_appel', 'video')
    
    if not destinataire_id:
        return jsonify({'error': 'Destinataire requis'}), 400
    
    appel_id = str(uuid.uuid4())
    
    appels_en_cours[appel_id] = {
        'appelant_id': session['user_id'],
        'appelant_nom': session['user_nom'],
        'destinataire_id': int(destinataire_id),
        'type': type_appel,
        'statut': 'en_cours',
        'date_debut': datetime.now().isoformat()
    }
    
    return jsonify({
        'success': True,
        'appel_id': appel_id,
        'room_name': appel_id
    })

@app.route('/api/appel/statut/<int:destinataire_id>')
def get_appel_statut(destinataire_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    for appel_id, appel in appels_en_cours.items():
        if appel['destinataire_id'] == session['user_id'] and appel['statut'] == 'en_cours':
            return jsonify({
                'appel_entrant': True,
                'appel_id': appel_id,
                'appelant_id': appel['appelant_id'],
                'appelant_nom': appel['appelant_nom'],
                'type': appel['type']
            })
    
    return jsonify({'appel_entrant': False})

@app.route('/api/appel/repondre', methods=['POST'])
def repondre_appel():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    appel_id = data.get('appel_id')
    accepte = data.get('accepte', False)
    
    if appel_id not in appels_en_cours:
        return jsonify({'error': 'Appel introuvable'}), 404
    
    if accepte:
        appels_en_cours[appel_id]['statut'] = 'accepte'
        return jsonify({
            'success': True,
            'room_name': appel_id,
            'type': appels_en_cours[appel_id]['type']
        })
    else:
        appels_en_cours[appel_id]['statut'] = 'refuse'
        del appels_en_cours[appel_id]
        return jsonify({'success': False, 'refuse': True})

@app.route('/api/appel/terminer', methods=['POST'])
def terminer_appel():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    appel_id = data.get('appel_id')
    
    if appel_id in appels_en_cours:
        del appels_en_cours[appel_id]
    
    return jsonify({'success': True})

@app.route('/appel/<room_name>/<type_appel>/<role>')
def appel_page(room_name, type_appel, role):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    if role == 'appelant':
        appel_info = appels_en_cours.get(room_name, {})
        autre_id = appel_info.get('destinataire_id')
    else:
        appel_info = appels_en_cours.get(room_name, {})
        autre_id = appel_info.get('appelant_id')
    
    if autre_id:
        cursor.execute("SELECT id, nom, photo_profil FROM users WHERE id = ?", (autre_id,))
        autre = cursor.fetchone()
    else:
        autre = None
    
    conn.close()
    
    return render_template('appel.html', 
                         autre=dict(autre) if autre else None, 
                         type_appel=type_appel, 
                         room_name=room_name, 
                         role=role, 
                         t=t)

# ==================== NOTIFICATIONS ====================

@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        flash('Veuillez vous connecter', 'warning')
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    notifications_list = []
    
    # Nouveaux messages non lus
    cursor.execute("""
        SELECT m.*, u.nom as expediteur_nom 
        FROM messages m
        JOIN users u ON m.expediteur_id = u.id
        WHERE m.destinataire_id = ? AND m.lu = 0
        ORDER BY m.date_envoi DESC
        LIMIT 20
    """, (session['user_id'],))
    messages_non_lus = cursor.fetchall()
    
    for msg in messages_non_lus:
        notifications_list.append({
            'type': 'new_message',
            'title': t('nouveau_message'),
            'message': f"{msg['expediteur_nom']}: {msg['contenu'][:50] if msg['contenu'] else '[Fichier]'}...",
            'date': msg['date_envoi'],
            'lien': f"/conversation/{msg['expediteur_id']}",
            'id': msg['id'],
            'lu': False
        })
    
    # Nouvelles publications
    cursor.execute("""
        SELECT id, description, categorie, date_publication 
        FROM publications 
        WHERE date_publication > date('now', '-7 days')
        ORDER BY date_publication DESC
        LIMIT 20
    """)
    nouvelles_pubs = cursor.fetchall()
    
    for pub in nouvelles_pubs:
        notifications_list.append({
            'type': 'new_publication',
            'title': t('nouvelle_publication'),
            'message': f"{pub['categorie']}: {pub['description'][:60]}...",
            'date': pub['date_publication'],
            'lien': f"/publications#{pub['id']}",
            'id': pub['id'],
            'lu': False
        })
    
    # Si admin: nouveaux utilisateurs
    if session.get('is_admin'):
        cursor.execute("""
            SELECT id, nom, email, date_inscription 
            FROM users 
            WHERE is_admin = 0 AND date_inscription > date('now', '-7 days')
            ORDER BY date_inscription DESC
            LIMIT 20
        """)
        nouveaux_users = cursor.fetchall()
        
        for user in nouveaux_users:
            notifications_list.append({
                'type': 'new_user',
                'title': t('nouvel_utilisateur'),
                'message': f"{user['nom']} ({user['email']}) vient de s'inscrire",
                'date': user['date_inscription'],
                'lien': f"/admin/editer-user/{user['id']}",
                'id': user['id'],
                'lu': False
            })
    
    notifications_list.sort(key=lambda x: x['date'], reverse=True)
    
    conn.close()
    
    return render_template('notifications.html', notifications=notifications_list, t=t)

@app.route('/api/notifications/count')
def api_notifications_count():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    
    result = {
        'messages_non_lus': 0,
        'nouvelles_publications': 0,
        'nouveaux_utilisateurs': 0
    }
    
    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE destinataire_id = ? AND lu = 0", (session['user_id'],))
    result['messages_non_lus'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM publications WHERE date_publication > date('now', '-7 days')")
    result['nouvelles_publications'] = cursor.fetchone()['count']
    
    if session.get('is_admin'):
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_admin = 0 AND date_inscription > date('now', '-7 days')")
        result['nouveaux_utilisateurs'] = cursor.fetchone()['count']
    
    conn.close()
    
    return jsonify(result)

# ==================== MODIFIER PUBLICATION ====================

@app.route('/admin/modifier-publication/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_modifier_publication(id):
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        description = request.form.get('description')
        categorie = request.form.get('categorie')
        type_media = request.form.get('type_media')
        
        fichier = None
        lien = None
        
        cursor.execute("SELECT fichier, lien_video, type FROM publications WHERE id = ?", (id,))
        old_pub = cursor.fetchone()
        
        if 'fichier' in request.files and request.files['fichier'].filename:
            file = request.files['fichier']
            if file and allowed_file(file.filename):
                if old_pub and old_pub['fichier']:
                    old_chemin = os.path.join(app.config['UPLOAD_FOLDER'], old_pub['fichier'])
                    if os.path.exists(old_chemin):
                        os.remove(old_chemin)
                
                extension = file.filename.rsplit('.', 1)[1].lower()
                nouveau_nom = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{extension}"
                chemin = os.path.join(app.config['UPLOAD_FOLDER'], nouveau_nom)
                file.save(chemin)
                fichier = nouveau_nom
        else:
            fichier = old_pub['fichier'] if old_pub else None
        
        if type_media == 'lien':
            lien = request.form.get('lien')
        
        cursor.execute("""
            UPDATE publications 
            SET description = ?, categorie = ?, type = ?, fichier = ?, lien_video = ?
            WHERE id = ?
        """, (description, categorie, type_media, fichier, lien, id))
        conn.commit()
        conn.close()
        
        flash(t('publication') + ' modifiée avec succès!', 'success')
        return redirect('/publications')
    
    cursor.execute("SELECT * FROM publications WHERE id = ?", (id,))
    publication = cursor.fetchone()
    conn.close()
    
    if not publication:
        flash('Publication non trouvée!', 'danger')
        return redirect('/publications')
    
    return render_template('admin/admin_modifier_publication.html', publication=dict(publication), t=t)

# ==================== API COMMENTAIRES ====================

@app.route('/ajouter-commentaire', methods=['POST'])
def ajouter_commentaire():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    publication_id = data.get('publication_id')
    texte = data.get('texte')
    parent_id = data.get('parent_id')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO commentaires (publication_id, user_id, parent_id, texte)
        VALUES (?, ?, ?, ?)
    """, (publication_id, session['user_id'], parent_id, texte))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/reagir-publication', methods=['POST'])
def reagir_publication():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    publication_id = data.get('publication_id')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM reactions WHERE publication_id=? AND user_id=?", 
                 (publication_id, session['user_id']))
    reaction = cursor.fetchone()
    
    if reaction:
        cursor.execute("DELETE FROM reactions WHERE id=?", (reaction['id'],))
        action = 'unlike'
    else:
        cursor.execute("INSERT INTO reactions (publication_id, user_id, type) VALUES (?, ?, 'like')", 
                     (publication_id, session['user_id']))
        action = 'like'
    
    cursor.execute("SELECT COUNT(*) as count FROM reactions WHERE publication_id=?", (publication_id,))
    nb_reactions = cursor.fetchone()['count']
    
    conn.commit()
    conn.close()
    return jsonify({'action': action, 'nb_reactions': nb_reactions})

@app.route('/reagir-commentaire', methods=['POST'])
def reagir_commentaire():
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    commentaire_id = data.get('commentaire_id')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM reaction_commentaires WHERE commentaire_id=? AND user_id=?", 
                 (commentaire_id, session['user_id']))
    reaction = cursor.fetchone()
    
    if reaction:
        cursor.execute("DELETE FROM reaction_commentaires WHERE id=?", (reaction['id'],))
        action = 'unlike'
    else:
        cursor.execute("INSERT INTO reaction_commentaires (commentaire_id, user_id) VALUES (?, ?)", 
                     (commentaire_id, session['user_id']))
        action = 'like'
    
    cursor.execute("SELECT COUNT(*) as count FROM reaction_commentaires WHERE commentaire_id=?", (commentaire_id,))
    nb_reactions = cursor.fetchone()['count']
    
    conn.commit()
    conn.close()
    return jsonify({'action': action, 'nb_reactions': nb_reactions})

# ==================== ADMIN ====================

@app.route('/admin/login')
def admin_login_page():
    if session.get('is_admin'):
        return redirect('/admin/ajouter')
    return render_template('admin/admin_login.html', t=t)

@app.route('/admin/verifier', methods=['POST'])
def admin_verifier():
    code = request.form.get('admin_code')
    if code == ADMIN_CODE:
        session['is_admin'] = True
        flash('Connecté en tant qu\'administrateur', 'success')
        return redirect('/admin/ajouter')
    else:
        flash('Mot de passe incorrect', 'danger')
        return redirect('/admin/login')

@app.route('/admin/ajouter')
@admin_required
def admin_ajouter():
    return render_template('admin/admin_ajouter.html', t=t)

@app.route('/admin/ajouter-publication', methods=['POST'])
@admin_required
def ajouter_publication():
    description = request.form.get('description')
    categorie = request.form.get('categorie')
    type_media = request.form.get('type_media')
    
    fichier = None
    lien = None
    
    if type_media == 'lien':
        lien = request.form.get('lien')
    else:
        file = request.files.get('fichier')
        if file and allowed_file(file.filename):
            extension = file.filename.rsplit('.', 1)[1].lower()
            nouveau_nom = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{extension}"
            chemin = os.path.join(app.config['UPLOAD_FOLDER'], nouveau_nom)
            file.save(chemin)
            fichier = nouveau_nom
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO publications (description, categorie, type, fichier, lien_video, date_publication)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (description, categorie, type_media, fichier, lien, datetime.now()))
    conn.commit()
    conn.close()
    
    flash('Publication ajoutée avec succès!', 'success')
    return redirect('/publications')

@app.route('/admin/supprimer-publication/<int:id>', methods=['POST'])
@admin_required
def supprimer_publication(id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT fichier FROM publications WHERE id = ?", (id,))
    pub = cursor.fetchone()
    
    if pub and pub['fichier']:
        chemin = os.path.join(app.config['UPLOAD_FOLDER'], pub['fichier'])
        if os.path.exists(chemin):
            os.remove(chemin)
    
    cursor.execute("DELETE FROM publications WHERE id = ?", (id,))
    cursor.execute("DELETE FROM commentaires WHERE publication_id = ?", (id,))
    cursor.execute("DELETE FROM reactions WHERE publication_id = ?", (id,))
    conn.commit()
    conn.close()
    
    flash('Publication supprimée!', 'success')
    return redirect('/publications')

@app.route('/admin/utilisateurs')
@admin_required
def admin_utilisateurs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nom, email, telephone, is_admin, en_ligne, date_inscription FROM users ORDER BY date_inscription DESC")
    users = cursor.fetchall()
    users_list = [dict(u) for u in users]
    conn.close()
    return render_template('admin/admin_utilisateurs.html', users=users_list, t=t)

@app.route('/admin/supprimer-user/<int:id>', methods=['POST'])
@admin_required
def admin_supprimer_user(id):
    if id == session.get('user_id'):
        flash('Vous ne pouvez pas vous supprimer vous-même!', 'danger')
        return redirect('/admin/utilisateurs')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Utilisateur supprimé!', 'success')
    return redirect('/admin/utilisateurs')

@app.route('/admin/editer-user/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_editer_user(id):
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        nom = request.form.get('nom')
        date_naissance = request.form.get('date_naissance')
        sexe = request.form.get('sexe')
        email = request.form.get('email')
        telephone = request.form.get('telephone')
        is_admin = 1 if request.form.get('is_admin') else 0
        
        cursor.execute("""
            UPDATE users 
            SET nom = ?, date_naissance = ?, sexe = ?, email = ?, telephone = ?, is_admin = ?
            WHERE id = ?
        """, (nom, date_naissance, sexe, email, telephone, is_admin, id))
        conn.commit()
        flash('Utilisateur modifié!', 'success')
        return redirect('/admin/utilisateurs')
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (id,))
    user = cursor.fetchone()
    user_dict = dict(user) if user else {}
    conn.close()
    return render_template('admin/admin_editer_user.html', user=user_dict, t=t)

# ==================== LANCEMENT ====================

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profils'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'messages'), exist_ok=True)
    os.makedirs('static/images', exist_ok=True)
    
    if os.path.exists('database.db'):
        print("⚠️ Base de données existante trouvée")
    
    init_db()
    
    print("\n" + "="*60)
    print("🚀 SERVEUR FAHSTUDIO DÉMARRÉ!")
    print("="*60)
    print("📌 Site: http://127.0.0.1:5000")
    print("👑 Admin: admin@fahstudio.com / admin123")
    print("🔑 Code admin: FAHSTUDIO2025")
    print("📱 WhatsApp: 038 09 421 19")
    print("="*60)
    print("🌍 LANGUES DISPONIBLES:")
    print("   🇫🇷 Français")
    print("   🇲🇬 Malagasy")
    print("="*60)
    print("🎥 FONCTIONNALITÉS:")
    print("   ✅ Appel vidéo et vocal")
    print("   ✅ Point vert pour utilisateurs en ligne")
    print("   ✅ Boutons flottants Messages/Notifications/WhatsApp")
    print("   ✅ Page notifications avec badges")
    print("   ✅ Admin peut modifier les publications")
    print("   ✅ Langue FR/MG qui change sur tout le site")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)