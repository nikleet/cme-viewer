## Local run

```bash
python -m server --mode local --data-dir .

or 

python -m server --mode local --data-dir /home/niklas/PSI/cme-viewer/dat/cmecme/cmecme_poly_part1_run1a_cme/cor_mhd
```
Browser opens automatically.

## Remote run (SSH tunnel)

### On local machine
```
ssh -L 8080:localhost:8080 user@q.predsci.com
```

### On server
```
./scripts/start_server.sh /path/to/data
```

Open in browser:
```
http://localhost:8080
```

