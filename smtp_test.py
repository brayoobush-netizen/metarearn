import smtplib

try:
    # Connect to Gmail SMTP
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()

    # Login with your Gmail + App Password
    server.login("metarearn@gmail.com", "tuwo eoof nmdo wyaj")

    # Send a test email
    server.sendmail("metarearn@gmail.com", "recipient@example.com", "Subject: Test\n\nThis is a test email.")
    print("✅ Email sent successfully!")

    server.quit()

except Exception as e:
    print("❌ Error:", e)