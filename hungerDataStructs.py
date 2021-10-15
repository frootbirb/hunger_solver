# Logging
from colorama import Fore as color, Style, init, deinit
from multiprocessing import Manager

class Logger:
    doLogging = False
    logDepth = ""

    def initialize():
        # initialize Colorama
        init()
        Logger.logDepth = ""

    def cleanup():
        # cleanup Colorama
        deinit()

    def s(prefix, district, copy, regions):
        if Logger.doLogging:
            if prefix == "+":
                prefix = color.GREEN + prefix
            elif prefix == "-":
                prefix = color.RED + prefix
                Logger.logDepth = Logger.logDepth[:-1]
            elif prefix == "!":
                prefix = color.YELLOW + prefix

            if True:
                fmt = Logger.logDepth + "{}" + " {}".format(sorted(regions, key=lambda region: region.code))
            else:
                fmt = "{}"

            print(fmt.format(
                  "{}".format(prefix) + Style.RESET_ALL +
                  " {}".format(district) + Style.RESET_ALL +
                  " {:21}".format(copy) + Style.RESET_ALL)
            )

            if prefix == color.GREEN + "+":
                Logger.logDepth += " "

# The data structures

class District:
    def __init__(self, index, metricID=None, maxAcceptable=float("inf")):
        self.regions = set()
        self.adj = {}
        self.metric = 0
        self.index = index
        self.remainingOverhead = maxAcceptable
        self.metricID = metricID

    def __gt__(self, other):
        return self.metric > other.metric

    def addRegion(self, region):
        # append the region into this district
        self.regions.add(region)
        # add the region's metric to the district's metric
        if self.index != 0:
            self.metric += region.metrics[self.metricID]
            self.remainingOverhead -= region.metrics[self.metricID]
        # remove this region from the adjacency list
        self.adj.pop(region.code, None)
        # for each adjacent region, add it to the adjacency list
        for adjCode in (code for code in region.adj if code not in self.regions):
            self.adj[adjCode] = self.adj.get(adjCode, 0) + 1

        if self.index != 0:     Logger.s("+", self.index, region.name, self.regions)

    def removeRegion(self, region):
        if region not in self.regions:
            return
        # remove the region from this district
        self.regions.remove(region)
        # subtract the region's metric to the district's metric
        if self.index != 0:
            self.metric -= region.metrics[self.metricID]
            self.remainingOverhead += region.metrics[self.metricID]
        # re-add this region to the adjacency list
        self.adj[region.code] = len([adjCode for adjCode in region.adj if adjCode in self.regions])
        if self.adj[region.code] == 0:
            self.adj.pop(region.code)
        # remove one from each adjacent region to this region
        for adjCode in (code for code in region.adj if code in self.adj):
            self.adj[adjCode] -= 1
            if self.adj[adjCode] == 0:
                self.adj.pop(adjCode)

        if self.index != 0:     Logger.s("-", self.index, region.name, self.regions)

    def isAdjacent(self, region):
        return len(self.adj) == 0 or region in self.adj

    def canAdd(self, region):
        return self.index == 0 or self.remainingOverhead >= region.metrics[self.metricID]

    def canRemove(self, region):
        # Get the regions in this district adjacent to the potential removal target
        adjRegions = [adjRegion for adjRegion in self.regions if adjRegion in region.adj]

        # If there aren't any neighbors, return True!
        if len(adjRegions) == 0:
            return True

        # Pick an arbitrary adjacent item to start from
        queue = [adjRegions.pop()]
        while len(queue) != 0:
            seed = queue.pop()
            while adjRegion := next((adjRegion for adjRegion in adjRegions if adjRegion in seed.adj), False):
                adjRegions.remove(adjRegion)
                queue.append(adjRegion)
            if len(adjRegions) == 0:
                return True
        return False

class Region:
    def __init__(self, code, metrics, adj):
        self.code = code
        self.metrics = metrics
        self.adj = set(adj)
        self.name = converter.abbrev_to_name[code]
        self.hash = hash(code)
        self.distances = { }

    def __str__(self):
        return self.code

    def __repr__(self):
        return self.code

    def __eq__(self, other):
        return self.code == other

    def __hash__(self):
        return self.hash

# Helper file reading function
import csv

scales = ["states", "counties"]
scale = scales[0]

if (scale == "states"):
    #           0            1          2            3            4           5
    metrics = ["Population","Firearms","Area (mi2)","Land (mi2)","GDP ($1m)","Food ($1k)"]
    bannedIndices = []
    allowed = [metric for index, metric in enumerate(metrics) if index not in bannedIndices]
    broken = [metric for metric in metrics if metric not in allowed]
    import assets.states.name_to_abbrev as converter
elif (scale == "counties"):
    #           0
    metrics = ["Population"]
    bannedIndices = []
    allowed = [metric for index, metric in enumerate(metrics) if index not in bannedIndices]
    broken = [metric for metric in metrics if metric not in allowed]
    import assets.counties.name_to_abbrev as converter

def getDistanceStep(distCode, regions):
    dist = 0
    distances = {region: (0 if region == distCode else -1) for region in regions}
    changed = True
    while changed:
        changed = False
        for region in (region for region in regions.values() if region.code in distances and distances[region.code] == dist):
            for code in (code for code in region.adj if code in distances and distances[code] == -1):
                changed = True
                distances[code] = dist + 1
        dist += 1
        print("Calculating distances: {:10.4f}%".format(100*list(regions.keys()).index(distCode)/len(regions)), end="\r")

    return { code: dist for code, dist in distances.items() if dist > 0 }

def populateDistances(regions):
    # Attempt to read in distance
    try:
        with open("assets/" + scale + "/distance.csv", encoding='utf8', newline='') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=',')
            for row in reader:
                name = row.pop("name")
                regions[name].distances = { code: int(dist) for code, dist in row.items() if dist }
    except:
        for code, region in regions.items():
            region.distances = getDistanceStep(code, regions)
        print()
        with open("assets/" + scale + "/distance.csv", "w", encoding='utf8', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, delimiter=',', fieldnames=["name"] + list(regions.keys()))
            writer.writeheader()
            for region in regions.values():
                newRow = region.distances.copy()
                newRow["name"] = region.code
                writer.writerow(newRow)

def readFile():
    # Read in adjacency
    adj = {}
    with open("assets/" + scale + "/adjacency.csv", encoding='utf8', newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        for row in reader:
            adj[row[0]] = row[1:]

    # Read in regions
    regions = {}
    with open("assets/" + scale + "/data.tsv", encoding='utf8', newline='') as csvfile:
        reader = csv.DictReader(csvfile, delimiter='\t')
        for row in reader:
            code = row["Region"]
            # Skip the Totals row
            if code == "Total":
                continue
            # add the region and metrics
            metrics = {key: int(value.strip().replace(',','')) for (key, value) in row.items() if key in allowed}
            regions[code] = Region(code, metrics, adj[code])

    populateDistances(regions)

    return regions
    
regionlist = readFile()

def debugCheckForMissingEntries(adj, regions):
    adj_set = set(adj.keys())
    name_set = set(converter.abbrev_to_name.keys())
    data_set = set(regions.keys())

    in_data_not_name = data_set - name_set
    in_data_not_adj = data_set - adj_set
    in_data = in_data_not_name | in_data_not_adj

    in_adj_not_name = adj_set - name_set
    in_adj_not_data = adj_set - data_set
    in_adj = in_adj_not_name | in_adj_not_data

    in_name_not_adj = name_set - adj_set
    in_name_not_data = name_set - data_set
    in_name = in_name_not_adj | in_name_not_data

    all_incomplete = in_data | in_adj | in_name

    for i in range(0,len(all_incomplete),50):
        subset = list(all_incomplete)[i:i+50]
        formatstr = "{:>5} " + "|{:^5}"*len(subset)

        print(formatstr.format("all", *subset))
        print(formatstr.format("adj", *[("y" if code in in_adj else "") for code in subset]))
        print(formatstr.format("name", *[("y" if code in in_name else "") for code in subset]))
        print(formatstr.format("data", *[("y" if code in in_data else "") for code in subset]))
        print()

    printByState = {}
    for name in [converter.abbrev_to_name[code] for code in all_incomplete]:
        state = name[-2:]
        if state not in printByState:
            printByState[state] = []
        printByState[state].append(name)

    import assets.states.name_to_abbrev as stateNamer
    for state in printByState:
        print("{}:".format(stateNamer.abbrev_to_name[state]))
        for region in printByState[state]:
            print("\t{} - {}".format(converter.name_to_abbrev[region], region))

def printDistances(distances):
    for distCode in distances:
        distList = []
        for k, v in distances[distCode].items():
            if v <= 0:
                distList.append(color.BLACK)
            elif v == 1:
                distList.append(color.WHITE)
            elif v == 2:
                distList.append(color.BLUE)
            elif v == 3:
                distList.append(color.CYAN)
            elif v == 4:
                distList.append(color.GREEN)
            elif v == 5:
                distList.append(color.YELLOW)
            elif v == 6:
                distList.append(color.MAGENTA)
            else:
                distList.append(color.RED)
            distList.append(k)
            distList.append(v)
        print("{} --> ".format(distCode) + "|".join(["{}{:2}:{:2}" + Style.RESET_ALL]*len(distances)).format(*distList))
    # Attempt to read in distance
    try:
        with open("assets/" + scale + "/distance.csv", encoding='utf8', newline='') as csvfile:
            distanceMatrix = {}
            reader = csv.DictReader(csvfile, delimiter=',')
            for row in reader:
                name = row.pop("name")
                distanceMatrix[name] = { code: int(dist) for code, dist in row.items() if dist }
    except:
        distanceMatrix = { region: getDistanceStep(region) for region in regionlist }
        print()
        with open("assets/" + scale + "/distance.csv", "w", encoding='utf8', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, delimiter=',', fieldnames=["name"] + list(distanceMatrix.keys()))
            writer.writeheader()
            for code, distances in distanceMatrix.items():
                newRow = distances.copy()
                newRow["name"] = code
                writer.writerow(newRow)

    return distanceMatrix