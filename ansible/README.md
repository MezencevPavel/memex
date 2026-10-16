# Ansible — развёртывание Memex

Каталог содержит playbook и inventory для автоматического развёртывания приложения Memex на чистом сервере CentOS Stream 9.

## Требования

- Ansible на управляющем сервере (`apt install -y ansible` на Ubuntu).
- SSH-ключ между управляющим и целевым сервером.
- Целевой сервер — CentOS Stream 9 (или RHEL 9, RockyLinux 9, AlmaLinux 9).

## Настройка

1. Скопируйте `inventory.ini.example` в `inventory.ini`:

   ```bash
   cp inventory.ini.example inventory.ini
