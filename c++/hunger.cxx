#include <iostream>
#include <map>
#include <string>

using namespace std;

// This is a state, county, city, whatever
class Zone
{
public:
	Zone(string code, map<string, float> metrics)
	: m_code(code)
	, m_name(code)
	, m_metrics(metrics)
	{ }

private:
	string m_code;
	string m_name;
	map<string, float> m_metrics;
};

class District
{
	
private:
	typedef map<string, Zone> ZoneMap;
	ZoneMap m_zones;
};

int main() {
	cout << "howdy" << endl;
	return 0;
}