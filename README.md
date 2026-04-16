## Local run

```bash
python  server.py --mode local --data_dir .
```

Browser opens automatically.

## Remote run (SSH tunnel)

### On local machine
```bash
ssh -L 8080:localhost:8080 user@q.predsci.com
```

### On server
```bash
./scripts/start_server.sh /path/to/data
```

Open in browser:
```
http://localhost:8080
```

## Notes for me
```bash
python server.py --mode remote --data_dir /home/niklas/PSI/cmecme/cmecme_poly_part1_run1a_cme/cor_mhd
```