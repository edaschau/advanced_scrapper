# DANGER!!!! This will delete the database!!!

sudo -i -u postgres

psql -d cryptonew

DROP TABLE crypto_links

\q

exit