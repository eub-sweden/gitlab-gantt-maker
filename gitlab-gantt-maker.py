import gitlab
import plotly.express as px
import plotly.io as pio
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import configparser
import math
import argparse


def datestr(date):
    return date.strftime("%Y-%m-%d")


def strip_tz(datestr):
    return datestr[0:10]


def datestr_add_a_day(date):
    d = datetime.fromisoformat(strip_tz(date))
    d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def datestr_subtract_a_day(date):
    d = datetime.fromisoformat(strip_tz(date))
    d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


# If a milestone does not have a due date,
# one year from now is assumed
end_of_time = datetime.now()
end_of_time += relativedelta(years=1)
end_of_time = datestr(end_of_time)


class GanttMaker:
    def __init__(self, filename, verbose=False):
        self.filename = filename
        self.tasks = []
        self.idx = 0
        self.colormap = {
            "Group Milestone": "green",
            "Project Milestone": "blue",
            "Issue": "goldenrod",
        }

    def __repr__(self):
        return str(pd.DataFrame(self.tasks))

    def add_task(self, name, start, finish, url, type="Issue"):
        hyperlink = f"""<a href="{url}", target="_black">o</a>"""
        self.tasks.append(
            dict(
                Index=self.idx,
                Task=name,
                Start=start,
                Finish=finish,
                Url=hyperlink,
                Resource=type,
            )
        )
        self.idx += 1

    def _annotate(self):
        for idx, row in self.df.iterrows():
            periods = pd.date_range(row["Start"], row["Finish"], freq="1D")
            center_pos = math.floor(len(periods) / 2)
            x_dates = periods[center_pos]
            self.fig.add_annotation(
                {
                    "x": x_dates,  # row["Finish"],
                    "y": row["Task"],
                    "text": row["Url"],
                    "align": "center",
                    "showarrow": False,
                }
            )

    def write(self):
        self.df = pd.DataFrame(self.tasks)
        self.fig = px.timeline(
            self.df,
            x_start="Start",
            x_end="Finish",
            y="Task",
        )
        self.fig.update_traces(
            marker_color=[self.colormap[r] for r in self.df.Resource]
        )
        self.fig.update_yaxes(autorange="reversed")
        self._annotate()
        with open(self.filename, "w") as f:
            f.write(pio.to_html(self.fig))


def extract_milestone(ms):
    start_date = ms.created_at if not ms.start_date else ms.start_date
    due_date = ms.due_date if ms.due_date else end_of_time
    return ms.title, strip_tz(start_date), strip_tz(due_date), ms.web_url


def extract_issue(i, start_date, due_date):
    if i.due_date:
        due = i.due_date
        start = datestr_subtract_a_day(due)
    else:
        start = start_date if i.created_at < start_date else i.created_at
        due = datestr_add_a_day(start)
    return i.title, strip_tz(start), strip_tz(due), i.web_url


def main():

    parser = argparse.ArgumentParser(
        prog="gitlab-gantt-maker",
        description="Makes a simple Gantt chart out of Gitlab milestones as a standalone HTML file using the Gitlab API",
    )
    parser.add_argument(
        "-c", "--config", help="configuration file path", type=str, default="config.ini"
    )
    parser.add_argument(
        "-o", "--output", help="HTML output file path", type=str, default="gantt.html"
    )
    parser.add_argument("-v", "--verbose", action="store_true")  # on/off flag
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config)
    try:
        cfg_token = config["gitlab"]["PersonalAccessToken"]
        cfg_inst = config["gitlab"]["Instance"]
        cfg_group = config["gitlab"]["Group"]
    except KeyError:
        print("Missing or incomplete configuration file")
        exit(1)

    # private token or personal token authentication (GitLab.com)
    gl = gitlab.Gitlab(cfg_inst, private_token=cfg_token)

    # make an API request to create the gl.user object. This is not required but may be useful
    # to validate your token authentication. Note that this will not work with job tokens.
    gl.auth()

    # Enable "debug" mode. This can be useful when trying to determine what
    # information is being sent back and forth to the GitLab server.
    # Note: this will cause credentials and other potentially sensitive
    # information to be printed to the terminal.
    # gl.enable_debug()

    g = gl.groups.list(search=cfg_group)

    if not g:
        print("Group not found or API permissions missing")
        exit(1)

    gc = GanttMaker(args.output)

    group = g[0]
    projlist = group.projects.list()

    # Group milestones
    for groupms in group.milestones.list(state="active"):
        gm = group.milestones.get(groupms.id)
        title, start_date, due_date, url = extract_milestone(gm)
        gc.add_task(title, start_date, due_date, url, "Group Milestone")

    # Project milestones
    for proj in projlist:
        p = gl.projects.get(proj.id)
        for pm in p.milestones.list(state="active"):
            title, start_date, due_date, url = extract_milestone(pm)
            gc.add_task(
                p.name + "/" + title, start_date, due_date, url, "Project Milestone"
            )
            for i in pm.issues():
                if not i.state == "closed":
                    ititle, istart_date, idue_date, url = extract_issue(
                        i, start_date, due_date
                    )
                    gc.add_task(ititle, istart_date, idue_date, url)

    if args.verbose:
        print(gc)
    gc.write()


if __name__ == "__main__":
    main()
