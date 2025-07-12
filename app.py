from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from mysql import connector
import hashlib
from functools import wraps
import random
import string

app = Flask(__name__)

# MySQL configurations
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'quiz_management'
}

app.config['SECRET_KEY'] = 'your_secret_key'

def get_db_connection():
    return connector.connect(**db_config)

@app.route('/')
def index():
    return redirect(url_for('signup'))

# Signup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # Get form data
        fullname = request.form['fullname']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        # Hash the password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        # Create connection
        conn = get_db_connection()
        # Create cursor with dictionary=True
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            # Check if email already exists
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            
            if user:
                flash('Email already exists')
                return redirect(url_for('signup'))
            
            # Insert new user
            cur.execute("""
                INSERT INTO users (fullname, email, password, role) 
                VALUES (%s, %s, %s, %s)
            """, (fullname, email, hashed_password, role))
            
            # Commit to DB
            conn.commit()
            
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
            
        except Exception as e:
            print(e)
            flash('An error occurred. Please try again.')
            return redirect(url_for('signup'))
        
        finally:
            # Close cursor and connection
            cur.close()
            conn.close()
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = get_db_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            cur.execute("SELECT * FROM users WHERE email = %s AND password = %s", 
                       (email, hashed_password))
            user = cur.fetchone()
            
            if user:
                session['user_id'] = user['id']
                session['role'] = user['role']
                session['fullname'] = user['fullname']
                
                # Redirect based on role
                if user['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif user['role'] == 'teacher':
                    return redirect(url_for('teacher_dashboard'))
                else:
                    return redirect(url_for('student_dashboard'))
            else:
                flash('Invalid email or password', 'error')
                
        except Exception as e:
            flash('An error occurred', 'error')
            print(e)
            
        finally:
            cur.close()
            conn.close()
            
    return render_template('login.html')

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Role required decorator
def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session or session['role'] not in allowed_roles:
                flash('Access denied', 'error')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

@app.route('/admin/dashboard')
@login_required
@role_required(['admin'])
def admin_dashboard():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Fetch users
    cur.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    
    # Fetch quizzes with teacher names
    cur.execute("""
        SELECT q.*, u.fullname as teacher_name 
        FROM quizzes q 
        JOIN users u ON q.teacher_id = u.id 
        ORDER BY q.created_at DESC
    """)
    quizzes = cur.fetchall()
    
    # Fetch marks with filter
    quiz_id = request.args.get('quiz_id')
    if quiz_id:
        cur.execute("""
            SELECT m.*, u.fullname as student_name, q.title as quiz_title
            FROM marks m
            JOIN users u ON m.student_id = u.id
            JOIN quizzes q ON m.quiz_id = q.id
            WHERE m.quiz_id = %s
            ORDER BY m.attempt_date DESC
        """, (quiz_id,))
    else:
        cur.execute("""
            SELECT m.*, u.fullname as student_name, q.title as quiz_title
            FROM marks m
            JOIN users u ON m.student_id = u.id
            JOIN quizzes q ON m.quiz_id = q.id
            ORDER BY m.attempt_date DESC
        """)
    marks = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('admin_dashboard.html', 
                         users=users, 
                         quizzes=quizzes, 
                         marks=marks)

@app.route('/get_quiz_details/<int:quiz_id>')
@login_required
@role_required(['admin'])
def get_quiz_details(quiz_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Fetch quiz details
    cur.execute("""
        SELECT q.*, u.fullname as teacher_name 
        FROM quizzes q 
        JOIN users u ON q.teacher_id = u.id 
        WHERE q.id = %s
    """, (quiz_id,))
    quiz = cur.fetchone()
    
    # Fetch questions
    cur.execute("SELECT * FROM questions WHERE quiz_id = %s", (quiz_id,))
    questions = cur.fetchall()
    
    # Fetch options for each question
    for question in questions:
        cur.execute("SELECT * FROM options WHERE question_id = %s", (question['id'],))
        question['options'] = cur.fetchall()
    
    quiz['questions'] = questions
    
    cur.close()
    conn.close()
    
    return jsonify(quiz)

@app.route('/toggle_quiz_status/<int:quiz_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def toggle_quiz_status(quiz_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Toggle the is_active status
        cur.execute("""
            UPDATE quizzes 
            SET is_active = NOT is_active 
            WHERE id = %s
        """, (quiz_id,))
        conn.commit()
        success = True
    except Exception as e:
        print(e)
        conn.rollback()
        success = False
    finally:
        cur.close()
        conn.close()
    
    return jsonify({'success': success})

@app.route('/delete_quiz/<int:quiz_id>')
@login_required
@role_required(['admin'])
def delete_quiz(quiz_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Delete related records first
        cur.execute("DELETE FROM marks WHERE quiz_id = %s", (quiz_id,))
        cur.execute("DELETE FROM options WHERE question_id IN (SELECT id FROM questions WHERE quiz_id = %s)", (quiz_id,))
        cur.execute("DELETE FROM questions WHERE quiz_id = %s", (quiz_id,))
        cur.execute("DELETE FROM quizzes WHERE id = %s", (quiz_id,))
        
        conn.commit()
        flash('Quiz deleted successfully', 'success')
    except Exception as e:
        print(e)
        conn.rollback()
        flash('Error deleting quiz', 'error')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('admin_dashboard'))

def generate_quiz_code():
    """Generate a random 6-character quiz code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@app.route('/teacher/dashboard')
@login_required
@role_required(['teacher'])
def teacher_dashboard():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Get teacher's quizzes
    cur.execute("""
        SELECT * FROM quizzes 
        WHERE teacher_id = %s 
        ORDER BY created_at DESC
    """, (session['user_id'],))
    quizzes = cur.fetchall()
    
    # Get enrolled students
    cur.execute("""
        SELECT u.*, e.created_at as enrollment_date
        FROM users u
        JOIN enrollments e ON u.id = e.student_id
        WHERE e.teacher_id = %s
        ORDER BY e.created_at DESC
    """, (session['user_id'],))
    enrolled_students = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('teacher_dashboard.html',
                         quizzes=quizzes,
                         enrolled_students=enrolled_students)

@app.route('/create_quiz', methods=['POST'])
@login_required
@role_required(['teacher'])
def create_quiz():
    if request.method == 'POST':
        title = request.form['title']
        subject = request.form['subject']
        duration = request.form['duration']
        description = request.form['description']
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # Generate unique quiz code
            while True:
                quiz_code = generate_quiz_code()
                cur.execute("SELECT id FROM quizzes WHERE code = %s", (quiz_code,))
                if not cur.fetchone():
                    break
            
            # Create quiz
            cur.execute("""
                INSERT INTO quizzes (title, subject, description, duration, code, teacher_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (title, subject, description, duration, quiz_code, session['user_id']))
            
            quiz_id = cur.lastrowid
            
            # Process questions
            questions = []
            i = 0
            while f'questions[{i}][text]' in request.form:
                question_text = request.form[f'questions[{i}][text]']
                marks = request.form[f'questions[{i}][marks]']
                correct_option = int(request.form[f'questions[{i}][correct]'])
                
                # Insert question
                cur.execute("""
                    INSERT INTO questions (quiz_id, question_text, marks)
                    VALUES (%s, %s, %s)
                """, (quiz_id, question_text, marks))
                
                question_id = cur.lastrowid
                
                # Insert options
                for j in range(4):
                    option_text = request.form[f'questions[{i}][options][{j}][text]']
                    is_correct = (j == correct_option)
                    cur.execute("""
                        INSERT INTO options (question_id, text, is_correct)
                        VALUES (%s, %s, %s)
                    """, (question_id, option_text, is_correct))
                
                i += 1
            
            conn.commit()
            flash('Quiz created successfully', 'success')
            
        except Exception as e:
            print(e)
            conn.rollback()
            flash('Error creating quiz', 'error')
            
        finally:
            cur.close()
            conn.close()
        
        return redirect(url_for('teacher_dashboard'))

@app.route('/view_quiz_results/<int:quiz_id>')
@login_required
@role_required(['teacher'])
def view_quiz_results(quiz_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Verify quiz belongs to teacher
    cur.execute("""
        SELECT * FROM quizzes 
        WHERE id = %s AND teacher_id = %s
    """, (quiz_id, session['user_id']))
    quiz = cur.fetchone()
    
    if not quiz:
        flash('Quiz not found', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Get quiz results
    cur.execute("""
        SELECT m.*, u.fullname as student_name,
               RANK() OVER (ORDER BY m.marks_obtained DESC) as rank
        FROM marks m
        JOIN users u ON m.student_id = u.id
        WHERE m.quiz_id = %s
        ORDER BY m.marks_obtained DESC
    """, (quiz_id,))
    results = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('quiz_results.html', quiz=quiz, results=results)

@app.route('/remove_student/<int:student_id>')
@login_required
@role_required(['teacher'])
def remove_student(student_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            DELETE FROM enrollments 
            WHERE student_id = %s AND teacher_id = %s
        """, (student_id, session['user_id']))
        conn.commit()
        flash('Student removed successfully', 'success')
    except Exception as e:
        print(e)
        conn.rollback()
        flash('Error removing student', 'error')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('teacher_dashboard'))

@app.route('/view_student_performance/<int:student_id>')
@login_required
@role_required(['teacher'])
def view_student_performance(student_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Verify student is enrolled with teacher
    cur.execute("""
        SELECT * FROM enrollments 
        WHERE student_id = %s AND teacher_id = %s
    """, (student_id, session['user_id']))
    if not cur.fetchone():
        flash('Student not found', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Get student details
    cur.execute("SELECT * FROM users WHERE id = %s", (student_id,))
    student = cur.fetchone()
    
    # Get student's performance in teacher's quizzes
    cur.execute("""
        SELECT m.*, q.title as quiz_title,
               RANK() OVER (PARTITION BY m.quiz_id ORDER BY m.marks_obtained DESC) as rank
        FROM marks m
        JOIN quizzes q ON m.quiz_id = q.id
        WHERE m.student_id = %s AND q.teacher_id = %s
        ORDER BY m.attempt_date DESC
    """, (student_id, session['user_id']))
    performance = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('student_performance.html', 
                         student=student, 
                         performance=performance)

@app.route('/student/dashboard')
@login_required
@role_required(['student'])
def student_dashboard():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Get available quizzes from enrolled teachers
    cur.execute("""
        SELECT q.*, u.fullname as teacher_name, 
               CASE WHEN m.id IS NOT NULL THEN TRUE ELSE FALSE END as attempted
        FROM quizzes q
        JOIN users u ON q.teacher_id = u.id
        JOIN enrollments e ON q.teacher_id = e.teacher_id
        LEFT JOIN marks m ON q.id = m.quiz_id AND m.student_id = %s
        WHERE e.student_id = %s AND q.is_active = TRUE
        ORDER BY q.created_at DESC
    """, (session['user_id'], session['user_id']))
    available_quizzes = cur.fetchall()
    
    # Get student's marks with rankings
    cur.execute("""
        SELECT m.*, q.title as quiz_title,
               RANK() OVER (PARTITION BY m.quiz_id ORDER BY m.marks_obtained DESC) as rank
        FROM marks m
        JOIN quizzes q ON m.quiz_id = q.id
        WHERE m.student_id = %s
        ORDER BY m.attempt_date DESC
    """, (session['user_id'],))
    marks = cur.fetchall()
    
    # Get available teachers
    cur.execute("""
        SELECT u.*, 
               CASE WHEN e.id IS NOT NULL THEN TRUE ELSE FALSE END as is_enrolled
        FROM users u
        LEFT JOIN enrollments e ON u.id = e.teacher_id AND e.student_id = %s
        WHERE u.role = 'teacher'
    """, (session['user_id'],))
    available_teachers = cur.fetchall()
    
    # Get enrolled teachers
    cur.execute("""
        SELECT u.*, e.created_at as enrollment_date
        FROM users u
        JOIN enrollments e ON u.id = e.teacher_id
        WHERE e.student_id = %s
    """, (session['user_id'],))
    enrolled_teachers = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('student_dashboard.html',
                         available_quizzes=available_quizzes,
                         marks=marks,
                         available_teachers=available_teachers,
                         enrolled_teachers=enrolled_teachers)

@app.route('/enroll_teacher', methods=['POST'])
@login_required
@role_required(['student'])
def enroll_teacher():
    teacher_id = request.form.get('teacher_id')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO enrollments (student_id, teacher_id)
            VALUES (%s, %s)
        """, (session['user_id'], teacher_id))
        conn.commit()
        flash('Successfully enrolled with teacher', 'success')
    except Exception as e:
        print(e)
        conn.rollback()
        flash('Error enrolling with teacher', 'error')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('student_dashboard'))

@app.route('/join_quiz', methods=['POST'])
@login_required
@role_required(['student'])
def join_quiz():
    quiz_code = request.form.get('quiz_code')
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    cur.execute("""
        SELECT q.* FROM quizzes q
        WHERE q.code = %s AND q.is_active = TRUE
    """, (quiz_code,))
    quiz = cur.fetchone()
    
    if quiz:
        return redirect(url_for('take_quiz', quiz_id=quiz['id']))
    else:
        flash('Invalid or expired quiz code', 'error')
        return redirect(url_for('student_dashboard'))

@app.route('/take_quiz/<int:quiz_id>')
@login_required
@role_required(['student'])
def take_quiz(quiz_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Check if student has already attempted this quiz
    cur.execute("""
        SELECT * FROM marks 
        WHERE student_id = %s AND quiz_id = %s
    """, (session['user_id'], quiz_id))
    if cur.fetchone():
        flash('You have already attempted this quiz', 'error')
        return redirect(url_for('student_dashboard'))
    
    # Get quiz details
    cur.execute("""
        SELECT q.* FROM quizzes q
        WHERE q.id = %s AND q.is_active = TRUE
    """, (quiz_id,))
    quiz = cur.fetchone()
    
    if not quiz:
        flash('Quiz not found or inactive', 'error')
        return redirect(url_for('student_dashboard'))
    
    # Get questions and options
    cur.execute("SELECT * FROM questions WHERE quiz_id = %s", (quiz_id,))
    questions = cur.fetchall()
    
    for question in questions:
        cur.execute("SELECT * FROM options WHERE question_id = %s", (question['id'],))
        question['options'] = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('take_quiz.html', quiz=quiz, questions=questions)

@app.route('/submit_quiz/<int:quiz_id>', methods=['POST'])
@login_required
@role_required(['student'])
def submit_quiz(quiz_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    try:
        # Get all questions for this quiz
        cur.execute("SELECT * FROM questions WHERE quiz_id = %s", (quiz_id,))
        questions = cur.fetchall()
        
        marks_obtained = 0
        total_marks = 0
        
        # Calculate marks
        for question in questions:
            total_marks += question['marks']
            selected_option_id = request.form.get(f"question_{question['id']}")
            
            if selected_option_id:
                cur.execute("""
                    SELECT * FROM options 
                    WHERE id = %s AND is_correct = TRUE
                """, (selected_option_id,))
                if cur.fetchone():
                    marks_obtained += question['marks']
        
        # Save marks
        cur.execute("""
            INSERT INTO marks (student_id, quiz_id, marks_obtained, total_marks)
            VALUES (%s, %s, %s, %s)
        """, (session['user_id'], quiz_id, marks_obtained, total_marks))
        
        conn.commit()
        flash(f'Quiz submitted successfully! You scored {marks_obtained}/{total_marks}', 'success')
        
    except Exception as e:
        print(e)
        conn.rollback()
        flash('Error submitting quiz', 'error')
        
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('student_dashboard'))

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    fullname = request.form.get('fullname')
    email = request.form.get('email')
    new_password = request.form.get('new_password')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if new_password:
            hashed_password = hashlib.sha256(new_password.encode()).hexdigest()
            cur.execute("""
                UPDATE users 
                SET fullname = %s, email = %s, password = %s 
                WHERE id = %s
            """, (fullname, email, hashed_password, session['user_id']))
        else:
            cur.execute("""
                UPDATE users 
                SET fullname = %s, email = %s 
                WHERE id = %s
            """, (fullname, email, session['user_id']))
        
        conn.commit()
        session['fullname'] = fullname
        session['email'] = email
        flash('Profile updated successfully', 'success')
        
    except Exception as e:
        print(e)
        conn.rollback()
        flash('Error updating profile', 'error')
        
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('student_dashboard'))

@app.route('/promote_to_admin/<int:user_id>', methods=['POST'])
@login_required
def promote_to_admin(user_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)  # Use dictionary cursor

        # Check if current user is admin
        cur.execute("SELECT role FROM users WHERE id = %s", (session['user_id'],))
        current_user = cur.fetchone()
        if not current_user or current_user['role'] != 'admin':
            return jsonify({'success': False, 'message': 'Unauthorized access'})

        # Check if target user exists and is not already an admin
        cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        if user['role'] == 'admin':
            return jsonify({'success': False, 'message': 'User is already an admin'})
        
        # Promote user to admin
        cur.execute("UPDATE users SET role = 'admin' WHERE id = %s", (user_id,))
        conn.commit()
        
        return jsonify({'success': True, 'message': 'User successfully promoted to admin'})

    except Exception as e:
        print(f"Error promoting user to admin: {e}")  # Log the error
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': 'Server error occurred'})

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.route('/remove_user/<int:user_id>', methods=['POST'])
@login_required
def remove_user(user_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)  # Use dictionary cursor

        # Check if current user is admin
        cur.execute("SELECT role FROM users WHERE id = %s", (session['user_id'],))
        current_user = cur.fetchone()
        if not current_user or current_user['role'] != 'admin':
            return jsonify({'success': False, 'message': 'Unauthorized access'})

        # Don't allow admin to remove themselves
        if user_id == session['user_id']:
            return jsonify({'success': False, 'message': 'Cannot remove your own account'})

        # Check if user exists
        cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})

        # Begin transaction
        cur.execute("BEGIN")
        
        # First remove marks
        cur.execute("DELETE FROM marks WHERE student_id = %s", (user_id,))
        
        # Remove enrollments
        cur.execute("DELETE FROM enrollments WHERE student_id = %s", (user_id,))
        
        # If user is a teacher, handle their quizzes
        if user['role'] == 'teacher':
            # Get all quiz IDs created by this teacher
            cur.execute("SELECT id FROM quizzes WHERE teacher_id = %s", (user_id,))
            quiz_ids = [row['id'] for row in cur.fetchall()]
            
            if quiz_ids:
                # Remove all options for questions in these quizzes
                cur.execute("""
                    DELETE FROM options 
                    WHERE question_id IN (
                        SELECT id FROM questions 
                        WHERE quiz_id IN %s
                    )
                """, (tuple(quiz_ids),))
                
                # Remove all questions for these quizzes
                cur.execute("DELETE FROM questions WHERE quiz_id IN %s", (tuple(quiz_ids),))
                
                # Remove marks for these quizzes
                cur.execute("DELETE FROM marks WHERE quiz_id IN %s", (tuple(quiz_ids),))
                
                # Finally remove the quizzes
                cur.execute("DELETE FROM quizzes WHERE id IN %s", (tuple(quiz_ids),))

        # Finally remove the user
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        
        # Commit transaction
        conn.commit()
        
        return jsonify({'success': True})

    except Exception as e:
        print(f"Error removing user: {e}")  # Log the error
        if conn:
            conn.rollback()  # Rollback on error
        return jsonify({'success': False, 'message': str(e)})

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.route('/get_user_details/<int:user_id>')
@login_required
@role_required(['admin'])
def get_user_details(user_id):
    try:
        print(f"Fetching details for user ID: {user_id}")
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        # Get basic user info - removed subject as it's not in users table
        cur.execute("""
            SELECT id, fullname, email, role, created_at, is_active 
            FROM users 
            WHERE id = %s
        """, (user_id,))
        user = cur.fetchone()
        
        if not user:
            print(f"User not found with ID: {user_id}")
            return jsonify({'error': 'User not found'})
            
        print(f"User data fetched: {user}")
        user['created_at'] = user['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        if user['role'] == 'student':
            # Get enrolled teachers - removed subject
            cur.execute("""
                SELECT users.fullname, enrollments.created_at as enrollment_date
                FROM enrollments 
                JOIN users ON enrollments.teacher_id = users.id
                WHERE enrollments.student_id = %s
                ORDER BY enrollments.created_at DESC
            """, (user_id,))
            user['enrolled_teachers'] = cur.fetchall()
            
            # Format enrollment dates
            for teacher in user['enrolled_teachers']:
                if teacher.get('enrollment_date'):
                    teacher['enrollment_date'] = teacher['enrollment_date'].strftime('%Y-%m-%d %H:%M:%S')
            
            # Get quiz attempts
            cur.execute("""
                SELECT quizzes.title as quiz_title, marks.marks_obtained, marks.total_marks, 
                       marks.attempt_date
                FROM marks 
                JOIN quizzes ON marks.quiz_id = quizzes.id
                WHERE marks.student_id = %s
                ORDER BY marks.attempt_date DESC
            """, (user_id,))
            user['quiz_attempts'] = cur.fetchall()
            
            # Format attempt dates
            for attempt in user['quiz_attempts']:
                if attempt.get('attempt_date'):
                    attempt['attempt_date'] = attempt['attempt_date'].strftime('%Y-%m-%d %H:%M:%S')
            
        elif user['role'] == 'teacher':
            # Get created quizzes
            cur.execute("""
                SELECT title, subject, created_at, is_active
                FROM quizzes
                WHERE teacher_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            user['created_quizzes'] = cur.fetchall()
            
            # Get enrolled students
            cur.execute("""
                SELECT users.fullname, users.email, enrollments.created_at as enrollment_date
                FROM enrollments
                JOIN users ON enrollments.student_id = users.id
                WHERE enrollments.teacher_id = %s
                ORDER BY enrollments.created_at DESC
            """, (user_id,))
            user['enrolled_students'] = cur.fetchall()
            
            # Format dates
            for quiz in user['created_quizzes']:
                if quiz.get('created_at'):
                    quiz['created_at'] = quiz['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            
            for student in user['enrolled_students']:
                if student.get('enrollment_date'):
                    student['enrollment_date'] = student['enrollment_date'].strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify(user)
        
    except Exception as e:
        print(f"Error getting user details: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Server error occurred'})
        
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)