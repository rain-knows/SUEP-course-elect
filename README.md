# SUEP-course-elect

An automation script for SUEP course selection.

## Usage

### Local environment

```bash
cp envconfig.example.py envconfig.py
vim envconfig.py                      # please edit the configuration
pip install -r requirements.txt
python main.py
```

### Docker

```bash
cp envconfig.example.py envconfig.py
vim envconfig.py                      # please edit the configuration
docker build -t suep-course-elect .
docker run -it suep-course-elect
```

### GUI Interface

A graphical user interface (GUI) has been added to the script. You can use the GUI to perform all the operations that were previously done through the command line.

To run the GUI, use the following command:

```bash
python gui.py
```

The GUI provides the following functionalities:
- Login
- Select Courses
- View Courses List
- Export Courses List

## Configuration

| Variable                  | Description                                                                |
| ------------------------- | -------------------------------------------------------------------------- |
| username                  | 8-digit student ID in string                                               |
| password                  | password at [IDS](https://ids.shiep.edu.cn)                                |
| skip_course_list          | Skip checking courses list                                                 |
| check_course_availability | Check course availability when listing courses                             |
| sheet_format              | The format of the exported sheet (`tsv` or `xlsx`, leave blank to disable) |
| default_courses_exps      | The default courses expressions                                            |
| interval                  | The interval between two requests (in seconds)                             |
| threads_interval          | The interval between two threads (in seconds)                              |

## About courses expressions

Each course expression creates a thread. A course expression consists of course IDs and logical operators, including `&&` (and), `||` (or), `;` (order). Support for long expressions is not very good, so it is recommended to use short expressions.

Here is an example:

```python
courses_exps = {
    'election_id_1': [
        '114&&514;810',
        '0721||1919',
    ],
    'election_id_2': [
        '1851;2588',
    ],
}
```

- Thread 1 will select 114 first, and then select 514 if 114 is selected successfully. Regardless of the previous results, select 810 at the end.
- Thread 2 will select 0721 first, if 0721 is failed to select, then select 1919. (If 0721 is selected successfully, then 1919 will not start.)
- After election_id_1 is finished, election_id_2 will start.

## About connecting to the course selection platform

As stated in the notice from [the Office of Academic Affairs of SUEP](https://jwc.shiep.edu.cn/), the course selection platform can only be accessed directly outside SUEP during the peak hours of course selection. During non-peak hours, users from outside SUEP will need to log in to the VPN to access the course selection platform.

If you cannot access the course selection platform, please try one of the following solutions:

### Solution 1: Use EasyConnect client

Software download:

- [English](https://vpn.shiep.edu.cn/com/installClient_en.html)
- [Chinese (Simplified)](https://vpn.shiep.edu.cn/com/installClient.html)

Documentation:

- [English](https://vpn.shiep.edu.cn/com/help_en/)
- [Chinese (Simplified)](https://vpn.shiep.edu.cn/com/help/)

### Solution 2: Use docker-easyconnect

- [GitHub](https://github.com/Hagb/docker-easyconnect)
- [Docker Hub](https://hub.docker.com/r/hagb/docker-easyconnect)

Documentation:

- [Chinese (Simplified)](https://github.com/Hagb/docker-easyconnect/blob/master/README.md)

TL;DR

```bash
docker run --device /dev/net/tun --cap-add NET_ADMIN -it --name easyconnect -p 127.0.0.1:10808:1080 -p 127.0.0.1:10809:8888 -e EC_VER=7.6.3 -e CLI_OPTS="-d vpn.shiep.edu.cn -u username -p password" hagb/docker-easyconnect:cli
export HTTP_PROXY=127.0.0.1:10809
export HTTPS_PROXY=127.0.0.1:10809
```

### Solution 3: Go to SUEP

Then use SUEP's network to access the course selection platform.

## Some words

Every student knows that online course selection is not fair. Everyone has different knowledge, experience, devices, network environment, etc. It is unreasonable to determine whether a person can choose the courses he/she wants in the future semester only by these conditions.

This program may increase the unfairness, but provides a way for people who don't know much about computers. (For those who only need to know a little about HTTP requests, capturing a packet and repeating it to select a course can be done in less than a minute.)

Please use this program reasonably, and don't set the request frequency too high to avoid putting too much pressure on the server. Please help those students who encounter difficulties in online course selection, with great power comes great responsibility, and this is what we should do.

As a PoC, the creation of this program is for the disappearance of this program. I hope this condition will be improved in the future.

## License

GPLv3

This program is provided as is, without warranty or liability, please see the LICENSE file for more details.

By using this program, you agree to the terms of the license.
