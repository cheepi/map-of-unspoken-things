# 📍 Map of Unspoken Things (MOUThings)

**Map of Unspoken Things** adalah aplikasi berbasis web yang memungkinkan pengguna untuk menitipkan pesan atau curhatan secara anonim pada titik koordinat tertentu di peta. Setiap pesan dilengkapi dengan integrasi lagu dari Spotify untuk menambah kesan emosional pada setiap cerita yang tertinggal.

Project ini dideploy menggunakan infrastruktur **Amazon Web Services (AWS)** untuk memenuhi tugas **UAS Cloud Computing**.

---

## 🚀 Fitur Utama
- **Interactive Map**: Penempatan pin cerita berdasarkan lokasi geografis (Latitude & Longitude).
- **Spotify Integration**: Pemutar musik otomatis (preview) berdasarkan link track Spotify yang dibagikan.
- **User Statistics**: Ringkasan jumlah cerita dan kontribusi pengguna di halaman profil.
- **Infrastructure as Code**: Deployment otomatis menggunakan AWS CloudFormation.

---

## 🛠️ Tech Stack
- **Backend**: Python 3 (Flask Framework)
- **Frontend**: HTML5, CSS3, JavaScript (Leaflet.js untuk Peta)
- **Database**: PostgreSQL (AWS RDS)
- **Web Server**: Gunicorn & AWS EC2 (t2.micro)

---

## ☁️ Arsitektur Cloud
Project ini menggunakan arsitektur terpisah antara Application Layer dan Database Layer untuk memastikan keamanan dan manajemen resource yang lebih baik:
1. **Amazon EC2**: Menjalankan web server Flask dan Gunicorn.
2. **Amazon RDS (PostgreSQL)**: Sebagai database persisten untuk menyimpan data user dan entries.
3. **Security Groups**: Pengaturan firewall untuk akses port 80 (HTTP), 22 (SSH), dan 5432 (PostgreSQL).
4. **Automated Provisioning**: Seluruh konfigurasi server, mulai dari instalasi dependencies (Python, Git, PostgreSQL client) hingga inisialisasi skema database (tabel & view), dilakukan secara otomatis melalui **User Data script** pada CloudFormation. Hal ini memastikan proses deployment bersifat *reproducible* dan konsisten.

---

## ⚙️ Cara Deployment (AWS CloudFormation)
Untuk menjalankan infrastruktur ini kembali, gunakan file `template.yaml` di AWS CloudFormation Console:

1. **Upload Template**: Gunakan file `template.yaml`.
2. **Parameters**: Masukkan KeyName EC2, DB Password, serta Spotify Client ID & Secret.
3. **Wait for Completion**: Tunggu status hingga `CREATE_COMPLETE`.
4. **Access Website**: Ambil URL dari tab **Outputs** di CloudFormation.

---

## 📝 Catatan Lab
Aplikasi ini dideploy di lingkungan **AWS Academy Learner Lab**. Karena kebijakan lab, IP Public bersifat dinamis dan sesi server terbatas pada durasi lab yang aktif.