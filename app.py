import os
from flask import Flask, render_template, request, session, send_from_directory, after_this_request
from werkzeug.utils import secure_filename
import subprocess as sp
import linkrot
from datetime import timedelta
import shutil
from linkrot.downloader import sanitize_url, get_status_code
from collections import defaultdict
import threadpool

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/'
app.secret_key = os.environ.get('APP_SECRET_KEY')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)

ALLOWED_EXTENSIONS = set(['pdf'])
MAX_THREADS_DEFAULT = 7


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def upload_form():
    return render_template('upload.html', flash='')


@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/loading')
def loading():
    return render_template('loading.html')


@app.route('/', methods=['POST'])
def upload_pdf():
    website = request.form['text']
    if website:
        if website.endswith('.pdf'):
            website = sanitize_url(website)
            session['file'] = website.split('/')[-1].split('.')[0]
            session['type'] = 'url'
            metadata, codes, pdfs, urls = pdfdata(website)
            return render_template('analysis.html', meta_titles=list(metadata.keys()), meta_values=list(metadata.values()), codes=codes, pdfs=pdfs, urls=urls)
        else:
            return render_template('upload.html', flash='pdf')
    else:
        if 'file' not in request.files:
            return render_template('upload.html', flash='')
        file = request.files['file']
        if file.filename == '':
            return render_template('upload.html', flash='none')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            session['file'] = filename.split('.')[0]
            session['type'] = 'file'
            file.save(path)
            metadata, codes, pdfs, urls = pdfdata(path)
            return render_template('analysis.html', meta_titles=list(metadata.keys()), meta_values=list(metadata.values()), codes=codes, pdfs=pdfs, urls=urls, filename=filename)
        else:
            return render_template('upload.html', flash='pdf')


def pdfdata(path):
    pdf = linkrot.linkrot(path)
    session['path'] = path
    metadata = pdf.get_metadata()
    refs = pdf.get_references()

    codes, urls, pdfs = check_status_codes(refs, max_threads=MAX_THREADS_DEFAULT)

    return metadata, dict(codes), pdfs, urls

def check_status_codes(refs, max_threads=MAX_THREADS_DEFAULT):
    codes = defaultdict(list)
    pdfs = []
    urls = []

    def check_url(ref):
        url = sanitize_url(ref.ref)
        if ref.reftype == 'url' or ref.reftype == 'pdf':
            status_code = get_status_code(url)
            codes[status_code].append([url, ref.page])

        if ref.reftype == 'url':
            urls.append([status_code, url])
        elif ref.reftype == 'pdf':
            pdfs.append([status_code, url])

    # Start a threadpool and add the check-url tasks
    try:
        pool = threadpool.ThreadPool(max_threads)
        pool.map(check_url, refs)
        pool.wait_completion()

    except Exception as e:
        print(e)
    except KeyboardInterrupt:
        pass

    return codes, urls, pdfs


@ app.route('/downloadpdf', methods=['GET', 'POST'])
def downloadpdf():
    @ after_this_request
    def remove_file(response):
        os.remove(app.config['UPLOAD_FOLDER']+session['file']+'.zip')
        return response
    download_folder_path = os.path.join(
        app.config['UPLOAD_FOLDER'], session['file'])
    os.mkdir(download_folder_path)
    linkrot.linkrot(session['path']).download_pdfs(download_folder_path)
    shutil.make_archive(
        app.config['UPLOAD_FOLDER']+session['file'], 'zip', download_folder_path)
    if session['type'] == 'file':
        os.remove(session['path'])
    shutil.rmtree(download_folder_path)
    return send_from_directory(app.config['UPLOAD_FOLDER'], session['file']+'.zip', as_attachment=True)


if __name__ == '__main__':
    app.run(port=5000)
